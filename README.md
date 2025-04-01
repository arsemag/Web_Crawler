# Web_Crawler


This Python program is a web crawler designed to log into Fakebook, a simulated website hosted at Northeastern University, and extract hidden secret flags. The program uses a combination of HTTP requests, HTML parsing, and session handling to navigate through the website, locate hidden flags, and print them.

Classes
AnchoredLinksParser (HTMLParser): Parses HTML to extract anchored links (href attributes). This parser collects links found in <a> tags.

FlagParser (HTMLParser): Parses HTML to extract the secret flag. When a "<h3>" tag with class "secret_flag" is encountered, it captures the flag text.

FakebookSession: Handles secure login and maintains session cookies.

Crawler: Manages the crawling process, keeping track of explored and unexplored links.

Methods
extract_links(html): Parses HTML pages to find new links.

extract_flag(html): Extracts and prints flags if found.

build_request(method, path, host, extra_headers, body): Constructs HTTP requests.

parse_response(raw_response): Parses HTTP responses.

recv_until_delimiter(sock: socket.socket, delimiter: bytes = b"\r\n\r\n"): Receives data from a socket until a specified delimiter is encountered.

login(self, username: str, password: str): Gets the login page to retrieve the initial CSRF token.

send_get(self, path: str, extra_headers: dict = None): Sends a GET request to the specified path including the stored cookies.
