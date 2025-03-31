#!/usr/bin/env python3
import argparse
import socket
import ssl
import os
import sys
import gzip
from html.parser import HTMLParser
from os import MFD_ALLOW_SEALING

from dotenv import load_dotenv

load_dotenv()

DEFAULT_SERVER = "fakebook.khoury.northeastern.edu"
DEFAULT_PORT = 443

class AnchoredLinksParser(HTMLParser):
    """
    Parses HTML to extract anchored links (href attributes).
    This parser collects links found in <a> tags.
    """
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and "fakebook" in value:
                    # print(f"DEBUG:\n{value}")
                    self.links.append(value)

class FlagParser(HTMLParser):
    """
    Parses HTML to extract the secret flag.
    When a <h3> tag with class "secret_flag" is encountered, it captures the flag text.
    """
    def __init__(self):
        super().__init__()
        self.flag = None
        self._capturing = False

    def handle_starttag(self, tag, attrs):
        if tag == "h3" and any(name == "class" and value == "secret_flag" for name, value in attrs):
            self._capturing = True

    def handle_endtag(self, tag):
        if tag == "h3":
            self._capturing = False

    def handle_data(self, data):
        if self._capturing and "FLAG" in data:
            # Assumes flag text starts after "FLAG: " (adjust as needed)
            self.flag = data.strip()[6:]

def extract_links(html: str) -> list:
    parser = AnchoredLinksParser()
    parser.feed(html)
    return parser.links

def extract_flag(html: str) -> bool:
    """
    Parses the provided HTML for a flag.
    Prints the flag if found, otherwise prints an error to stderr.
    """
    parser = FlagParser()
    parser.feed(html)
    if parser.flag:
        print(parser.flag)
        return True
    else:
        return False
    # else:
        # print("Flag not found.", file=sys.stderr)

def build_request(method: str, path: str, host: str, extra_headers: dict = None, body: str = "") -> str:
    """
    Constructs an HTTP request string with common headers.
    """
    headers = {
        "Host": host,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "TE": "trailers"
    }
    if extra_headers:
        headers.update(extra_headers)
    if body and "Content-Length" not in headers:
        headers["Content-Length"] = str(len(body))
    request_line = f"{method} {path} HTTP/1.1"
    headers_str = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
    return f"{request_line}\r\n{headers_str}\r\n\r\n{body}"

def parse_response(raw_response: str) -> dict:
    """
    Parses a raw HTTP response string into its components.
    """
    try:
        header_section, body = raw_response.split("\r\n\r\n", 1)
    except ValueError:
        header_section, body = raw_response, ""
    lines = header_section.split("\r\n")
    status_line = lines[0]
    headers = {}
    for line in lines[1:]:
        if ": " in line:
            key, value = line.split(": ", 1)
            headers[key] = value
    return {"status_line": status_line, "headers": headers, "body": body}

def recv_until_delimiter(sock: socket.socket, delimiter: bytes = b"\r\n\r\n") -> bytes:
    """
    Receives data from a socket until a specified delimiter is encountered.
    """
    buffer = b""
    while True:
        chunk = sock.recv(2048)
        buffer += chunk
        if delimiter in buffer:
            break

    header_part, remainder = buffer.split(delimiter, 1)
    responses = parse_response(header_part.decode("ascii"))
    try:
        content_length = int(responses["headers"]["content-length"])
    except KeyError:
        print("key_error!", file=sys.stderr)
    body_data = remainder
    bytes_needed = content_length - len(body_data)
    while bytes_needed > 0:
        chunk = sock.recv(min(2048, bytes_needed))
        body_data += chunk
        bytes_needed = content_length - len(body_data)

    return header_part + delimiter + body_data

class FakebookSession:
    """
    A session that holds the CSRF token and session ID.
    This class encapsulates the connection, login, and subsequent GET requests
    using the stored cookies.
    """
    def __init__(self, server: str, port: int):
        self.server = server
        self.port = port
        self.csrf_token = None
        self.session_id = None
        self.secure_sock = None

    def connect(self):
        context = ssl.create_default_context()
        sock = socket.create_connection((self.server, self.port))
        self.secure_sock = context.wrap_socket(sock, server_hostname=self.server)

    def login(self, username: str, password: str) -> str:
        # GET login page to retrieve initial CSRF token
        get_req = build_request("GET", "/accounts/login/", self.server)
        self.secure_sock.sendall(get_req.encode("ascii"))
        response_data = recv_until_delimiter(self.secure_sock)
        response_text = response_data.decode("ascii", errors="replace")
        response = parse_response(response_text)
        csrf_token = ""
        csrf_cookie = response['headers'].get('set-cookie', "")
        if csrf_cookie:
            token_parts = csrf_cookie.split("; ")[0].split("=")
            if len(token_parts) == 2:
                csrf_token = token_parts[1]
        self.csrf_token = csrf_token

        # POST login credentials with CSRF token
        body = f"username={username}&password={password}&csrfmiddlewaretoken={self.csrf_token}&next=%2Ffakebook%2F"
        post_headers = {
            "Referer": f"https://{self.server}/accounts/login/?next=/fakebook/",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": f"https://{self.server}",
            "Cookie": f"csrftoken={self.csrf_token}"
        }
        post_req = build_request("POST", "/accounts/login/", self.server, extra_headers=post_headers, body=body)
        self.secure_sock.sendall(post_req.encode("ascii"))
        post_response_data = recv_until_delimiter(self.secure_sock)
        post_response_text = post_response_data.decode("ascii", errors="replace")
        post_response = parse_response(post_response_text)

        # Extract session ID from response cookies
        session_id = ""
        session_cookie = post_response['headers'].get('set-cookie', "")
        if "sessionid=" in session_cookie:
            try:
                session_id = session_cookie.split("; ")[0].split('=')[1]
            except IndexError:
                session_id = ""
        self.session_id = session_id

        # Follow redirect after login using updated cookies
        redirect_path = post_response['headers'].get("location", "/fakebook/")
        redirect_headers = {'Cookie': f"csrftoken={self.csrf_token}; sessionid={self.session_id}"}
        redirect_req = build_request("GET", redirect_path, self.server, extra_headers=redirect_headers)
        self.secure_sock.sendall(redirect_req.encode("ascii"))
        redirect_response_data = recv_until_delimiter(self.secure_sock)
        redirect_response_text = redirect_response_data.decode("ascii", errors="replace")
        redirect_response = parse_response(redirect_response_text)
        return redirect_response['body']

    def send_get(self, path: str, extra_headers: dict = None) -> dict:
        """
        Sends a GET request to the specified path including the stored cookies.
        """
        headers = extra_headers.copy() if extra_headers else {}
        # Automatically include the CSRF and session cookies if available.
        if self.csrf_token or self.session_id:
            headers["Cookie"] = f"csrftoken={self.csrf_token}; sessionid={self.session_id}"
        request = build_request("GET", path, self.server, extra_headers=headers)
        self.secure_sock.sendall(request.encode("ascii"))
        response_data = recv_until_delimiter(self.secure_sock)
        return parse_response(response_data.decode("ascii"))

class Crawler:
    """
    A simple crawler that connects to the given server, logs in, and
    processes the login response as well as subsequent pages using the persistent session.
    """
    def __init__(self, server: str, port: int, username: str, password: str):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.unexplored_pages = []
        self.explored_pages = []

    def run(self):
        # print("program started")
        flags_found = 0
        # print(f"Connecting to {self.server}:{self.port}")
        session = FakebookSession(self.server, self.port)
        session.connect()

        # Login and capture the returned page (e.g., home or redirect page)
        body = session.login(self.username, self.password)
        extract_flag(body)

        self.explored_pages.extend(['/accounts/login/', '/fakebook/'])
        links = extract_links(body)
        for link in links:
            if link not in self.explored_pages:
                self.unexplored_pages.append(link)

        while self.unexplored_pages:
            link = self.unexplored_pages.pop(0)
            if link in self.explored_pages:
                continue
            self.explored_pages.append(link)
            response = session.send_get(link)
            # print(f"REQUEST to {link}")
            # print(f"RESPONSE:\n{response}")
            if response['status_line'] == "HTTP/1.1 200 OK":
                if extract_flag(response['body']):
                    flags_found += 1
                if flags_found == 5:
                    # print("Program ended")
                    exit(0)
                new_links = extract_links(response['body'])
                for new_link in new_links:
                    if new_link not in self.explored_pages and new_link not in self.unexplored_pages:
                        # print(f'DEBUG: adding {new_link}')
                        # print(f'DEBUG: \nlength of explored pages: {len(self.explored_pages)}\nlength of unexplored pages: {len(self.unexplored_pages)}')
                        self.unexplored_pages.append(new_link)
            elif response['status_line'] == "HTTP/1.1 302 Found":
                # For redirects, add the location to the front of the queue.
                self.unexplored_pages.insert(0, response['headers'].get('location', ''))

def main():
    parser = argparse.ArgumentParser(description="Fakebook crawler")
    parser.add_argument('-s', dest="server", type=str, default=DEFAULT_SERVER, help="Server to crawl")
    parser.add_argument('-p', dest="port", type=int, default=DEFAULT_PORT, help="Port to use")
    parser.add_argument('username', type=str, help="Username for login")
    parser.add_argument('password', type=str, help="Password for login")
    args = parser.parse_args()
    crawler = Crawler(args.server, args.port, args.username, args.password)
    crawler.run()

if __name__ == "__main__":
    main()
