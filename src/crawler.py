#!/usr/bin/env python3
import argparse
import socket
import ssl
import os
import sys
import gzip
from html.parser import HTMLParser
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
                if name == "href":
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

def extract_flag(html: str) -> None:
    """
    Parses the provided HTML for a flag.
    Prints the flag if found, otherwise prints an error to stderr.
    """
    parser = FlagParser()
    parser.feed(html)
    if parser.flag:
        print(f"Flag found: {parser.flag}")
    else:
        print("Flag not found.", file=sys.stderr)

def build_request(method: str, path: str, host: str, extra_headers: dict = None, body: str = "") -> str:
    """
    Constructs an HTTP request string with common headers.

    Args:
        method (str): The HTTP method (e.g., 'GET', 'POST').
        path (str): The path of the resource being requested.
        host (str): The host name of the server.
        extra_headers (dict, optional): Additional headers to include in the request. Defaults to None.
        body (str, optional): The body of the request, if any. Defaults to an empty string.

    Returns:
        str: The constructed HTTP request string.
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
    Parses a raw HTTP response string into its status, headers, and body.
    """
    print(f"DEBUG:\n{raw_response}")
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

    Args:
        sock (socket.socket): The socket from which to receive data.
        delimiter (bytes, optional): The delimiter to look for in the received data. Defaults to b"\r\n\r\n".

    Returns:
        bytes: The received data, including the delimiter. If the data after the delimiter is gzip-compressed, it is decompressed.
    """
    buffer = b""
    while delimiter not in buffer:
        chunk = sock.recv(2048)
        if not chunk:
            break
        buffer += chunk
    parts = buffer.split(delimiter, 1)
    if len(parts) == 2:
        headers, body = parts
        try:
            body = gzip.decompress(body)
        except (OSError, EOFError):
            # Not gzip-compressed; leave as is
            pass
        return headers + delimiter + body
    return buffer

def perform_login(sock: socket.socket, host: str, username: str, password: str) -> str:
    """
    Logs into Fakebook via the provided socket connection.
    Returns the body of the redirect page after login.
    """
    # GET login page
    get_headers = {"Cookie": "csrftoken=k2puPprfwGcax6xuFgEWiBbKniO7Q1CK"}
    get_req = build_request("GET", "/accounts/login/?next=/fakebook/", host, extra_headers=get_headers)
    print(f"Sending GET login page:\n{get_req}")
    sock.sendall(get_req.encode("ascii"))
    response_data = recv_until_delimiter(sock)
    response_text = response_data.decode("ascii", errors="replace")
    response = parse_response(response_text)
    print(f"Received response:\n{response_text}")

    # Extract CSRF token from the set-cookie header
    csrf_token = ""
    csrf_cookie = response['headers'].get('set-cookie', "")
    if csrf_cookie:
        token_parts = csrf_cookie.split("; ")[0].split("=")
        if len(token_parts) == 2:
            csrf_token = token_parts[1]

    # POST login credentials
    body = f"username={username}&password={password}&csrfmiddlewaretoken={csrf_token}&next=%2Ffakebook%2F"
    post_headers = {
        "Referer": f"https://{host}/accounts/login/?next=/fakebook/",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": f"https://{host}",
        "Cookie": f"csrftoken={csrf_token}"
    }
    post_req = build_request("POST", "/accounts/login/", host, extra_headers=post_headers, body=body)
    print(f"Sending POST login details:\n{post_req}")
    sock.sendall(post_req.encode("ascii"))
    post_response_data = recv_until_delimiter(sock)
    post_response_text = post_response_data.decode("ascii", errors="replace")
    print(f"Received POST response:\n{post_response_text}")
    post_response = parse_response(post_response_text)

    # Extract session ID from the set-cookie header
    session_id = ""
    session_cookie = post_response['headers'].get('set-cookie', "")
    if "Lax; " in session_cookie:
        try:
            session_id = session_cookie.split("Lax; ")[1].split('; ')[0].split('=')[1]
        except IndexError:
            session_id = ""

    print(f"Session ID: {session_id}")

    # Follow redirect after login
    redirect_path = post_response['headers'].get("location", "/fakebook/")
    get_redirect_headers = {'Cookie': f"csrftoken={csrf_token}; sessionid={session_id}"}
    redirect_req = build_request("GET", redirect_path, host, extra_headers=get_redirect_headers)
    print(f"Sending redirect GET:\n{redirect_req}")
    sock.sendall(redirect_req.encode("ascii"))
    redirect_response_data = recv_until_delimiter(sock)
    redirect_response_text = redirect_response_data.decode("ascii", errors="replace")
    print(f"Received redirect response:\n{redirect_response_text}")
    redirect_response = parse_response(redirect_response_text)
    return redirect_response['body']

class Crawler:
    """
    A simple crawler that connects to the given server, logs in, and processes the login response.
    """
    def __init__(self, server: str, port: int, username: str, password: str):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.unexplored_pages = []
        self.explored_pages = []

    def run(self):
        print(f"Connecting to {self.server}:{self.port}")
        context = ssl.create_default_context()
        with socket.create_connection((self.server, self.port)) as sock:
            with context.wrap_socket(sock, server_hostname=self.server) as secure_sock:
                body = perform_login(secure_sock, self.server, self.username, self.password)
                # Process the returned HTML (for example, extract a flag)
                extract_flag(body)
                # Future work: Use AnchoredLinksParser to find and crawl additional pages.

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
