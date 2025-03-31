from unittest import TestCase
import unittest
from unittest.mock import MagicMock, Mock
from crawler import build_request, recv_until_delimiter
import socket
import gzip
class Test(TestCase):
    def test_get_request(self):
        expected_request = (
            "GET /test/path HTTP/1.1\r\n"
            "Host: example.com\r\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0\r\n"
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
            "Accept-Language: en-US,en;q=0.5\r\n"
            "Connection: keep-alive\r\n"
            "Upgrade-Insecure-Requests: 1\r\n"
            "TE: trailers\r\n\r\n"
        )
        result = build_request("GET", "/test/path", "example.com")
        self.assertEqual(result, expected_request)

    def test_builds_post_request_with_body_and_headers(self):
        extra_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        body = "key=value"
        expected_request = (
            "POST /submit HTTP/1.1\r\n"
            "Host: example.com\r\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0\r\n"
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
            "Accept-Language: en-US,en;q=0.5\r\n"
            "Connection: keep-alive\r\n"
            "Upgrade-Insecure-Requests: 1\r\n"
            "TE: trailers\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Content-Length: 9\r\n\r\n"
            "key=value"
        )
        self.assertEqual(build_request("POST", "/submit", "example.com", extra_headers, body), expected_request)

    def test_builds_request_with_additional_headers(self):
        extra_headers = {"X-Custom-Header": "CustomValue"}
        expected_request = (
            "GET /path HTTP/1.1\r\n"
            "Host: example.com\r\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0\r\n"
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
            "Accept-Language: en-US,en;q=0.5\r\n"
            "Connection: keep-alive\r\n"
            "Upgrade-Insecure-Requests: 1\r\n"
            "TE: trailers\r\n"
            "X-Custom-Header: CustomValue\r\n\r\n"
        )
        self.assertEqual(build_request("GET", "/path", "example.com", extra_headers), expected_request)

    def test_builds_request_with_empty_body(self):
        expected_request = (
            "POST /submit HTTP/1.1\r\n"
            "Host: example.com\r\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0\r\n"
            "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
            "Accept-Language: en-US,en;q=0.5\r\n"
            "Connection: keep-alive\r\n"
            "Upgrade-Insecure-Requests: 1\r\n"
            "TE: trailers\r\n\r\n"
        )
        self.assertEqual(build_request("POST", "/submit", "example.com"), expected_request)


class TestRecvUntilDelimiter(unittest.TestCase):
    def test_recv_until_delimiter(self):
        # Mock socket
        mock_socket = Mock(spec=socket.socket)

        # Simulate receiving data in chunks
        body = gzip.compress(b"Hello, world!")
        mock_socket.recv = MagicMock(side_effect=[
            b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\n" + body + b""
        ])

        # Expected result
        expected_result = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\nHello, world!"

        # Call the function
        result = recv_until_delimiter(mock_socket)

        # Assert the result
        self.assertEqual(expected_result, result)

    def test_receive_until_delimiter_with_html(self):
        with open("test_html.html", "rb") as file:
            html = file.read()
        compressed_html = gzip.compress(html)
        # print(gzip.compress(html))
        # print("DEBUG")
        # print(gzip.decompress(compressed_html[:846]).decode('ascii'))
        #
        # gzipped_html = gzip.compress(html)

        # Mock socket
        mock_socket = Mock(spec=socket.socket)

        # Simulate receiving data in chunks
        mock_socket.recv = MagicMock(side_effect=[
            b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\n" + compressed_html + b""
        ])

        # Expected result
        expected_result = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\n" + gzip.decompress(compressed_html) + b""

        # Call the function
        result = recv_until_delimiter(mock_socket)

        # Assert the result
        self.assertEqual(expected_result, result)
