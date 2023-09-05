#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# The MIT License
#
# Copyright (c) 2019-, Rick Lan, dragonpilot community, and a number of other of contributors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import os
import signal
import threading
import socket
from openpilot.common.realtime import set_core_affinity, set_realtime_priority


HOST = '0.0.0.0'
PORT = 9000
DEFAULT_DIR = '/data/media/0/realdata'

def list_directory(client_socket, path):
  try:
    # Check if the path is a directory
    if os.path.isdir(path):
      # Generate the directory listing HTML
      entries = os.listdir(path)
      directories = []
      files = []
      for entry in sorted(entries, reverse=True):
        full_path = os.path.join(path, entry)
        if os.path.isdir(full_path):
          directories.append(entry)
        else:
          files.append(entry)

      # Generate the HTML response
      content = "<!DOCTYPE html>"
      content += "<html>"
      content += "<head>"
      content += "<meta name='viewport' content='width=device-width, initial-scale=1'>"
      content += "<title>dragonpilot FileServ</title>"
      content += "</head>"
      content += "<body>"
      content += "<h3>Directories:</h3>"
      content += "<ul>"
      if path != DEFAULT_DIR:
        content += "<li><a href='..'>.. (Parent Directory)</a></li>"
      for directory in directories:
        content += f"<li><a href='{directory}/'>{directory}</a></li>"
      content += "</ul>"
      content += "<h3>Files:</h3>"
      content += "<ul>"
      for file in files:
        # file_extension = os.path.splitext(file)[1].lower()
        # if file_extension == '.hevc':
        #   content += f"<li><video src='{file}' controls><source type='video/x-hevc' src='{file}'></source></video></li>"
        # elif file_extension == '.ts':
        #   content += f"<li><video src='{file}' controls><source type='video/mp2t' src='{file}'></source></video></li>"
        # else:
        #   content += f"<li><a href='{file}'>{file}</a></li>"
        content += f"<li><a href='{file}'>{file}</a></li>"
      content += "</ul>"
      content += "</body>"
      content += "</html>"
      content = content.encode("utf-8")

      # Set the appropriate headers and write the response
      response = "HTTP/1.1 200 OK\r\n"
      response += "Content-Type: text/html\r\n"
      response += "Content-Length: " + str(len(content)) + "\r\n"
      response += "\r\n"
      response += content.decode()
      client_socket.sendall(response.encode())
    else:
      # If it's not a directory, use the default directory listing
      response = "HTTP/1.1 404 Not Found\r\n\r\n"
      client_socket.sendall(response.encode())
  except PermissionError:
    response = "HTTP/1.1 403 Forbidden\r\n\r\n"
    client_socket.sendall(response.encode())

def handle_request(client_socket):
  try:
    request = client_socket.recv(1024).decode()
    request_lines = request.split('\r\n')

    # Check if the request has any valid lines
    if request_lines and len(request_lines) > 0:
      # Get the requested path from the first line of the request
      first_line = request_lines[0]
      split_line = first_line.split()
      if len(split_line) > 1:
        path = split_line[1]
        if path == '/':
          path = DEFAULT_DIR
        else:
          path = os.path.join(DEFAULT_DIR, path.lstrip('/'))

        # Check if the requested path is a file
        if os.path.isfile(path):
          file_extension = os.path.splitext(path)[1].lower()
          if file_extension == '.hevc':
            content_type = "video/x-hevc"
          elif file_extension == '.ts':
            content_type = "video/mp2t"
          else:
            content_type = "application/octet-stream"
          file_size = os.path.getsize(path)
          response = "HTTP/1.1 200 OK\r\n"
          response += f"Content-Type: {content_type}\r\n"
          response += f"Content-Length: {file_size}\r\n"
          response += f"Content-Disposition: inline; filename={os.path.basename(os.path.dirname(path))}_{os.path.basename(path)}\r\n"
          response += "\r\n"
          client_socket.sendall(response.encode())

          with open(path, 'rb') as file:
            chunk_size = 8192
            while True:
              chunk = file.read(chunk_size)
              if not chunk:
                break
              try:
                client_socket.sendall(chunk)
              except BrokenPipeError:
                # Ignore broken pipe error if the client closes the connection
                break

        else:
          list_directory(client_socket, path)
      else:
        # If no valid path found in the request, send an error response
        response = "HTTP/1.1 400 Bad Request\r\n\r\n"
        client_socket.sendall(response.encode())
    else:
      # If no valid lines found in the request, send an error response
      response = "HTTP/1.1 400 Bad Request\r\n\r\n"
      client_socket.sendall(response.encode())

  except ConnectionResetError:
    # Ignore connection reset error if the client closes the connection
    pass

  client_socket.close()


def start_server():
  server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  server_socket.bind((HOST, PORT))
  server_socket.listen(1)
  # print(f'Server listening on {HOST}:{PORT}')

  try:
    while True:
      client_socket, client_address = server_socket.accept()
      # print(f'Connected by {client_address[0]}:{client_address[1]}')
      handle_request(client_socket)
  except KeyboardInterrupt:
    server_socket.close()

# Create a separate thread to handle serving the requests
server_thread = threading.Thread(target=start_server)

# Register a signal handler for SIGINT (Ctrl+C) to gracefully shutdown the server
def signal_handler(sig, frame):
  # print("Shutting down the server...")
  server_thread.join()
  # print("Server stopped.")
  os._exit(0)

def main():
  set_core_affinity([1,])
  set_realtime_priority(1)

  # Create a separate thread to handle serving the requests
  server_thread = threading.Thread(target=start_server)

  # Register a signal handler for SIGINT (Ctrl+C) to gracefully shutdown the server
  signal.signal(signal.SIGINT, signal_handler)

  # Start the server thread
  server_thread.start()

if __name__ == "__main__":
  main()
