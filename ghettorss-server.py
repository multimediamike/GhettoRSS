#!/usr/bin/python

# ghettorss-server.py
# part of GhettoRSS by Mike Melanson (mike -at- multimedia.cx)

import BaseHTTPServer
import getopt
import json
import os
import sqlite3
import sys

SQLITE_DATABASE = "ghettorss.sqlite3"
STATIC_DIR = "/static/"
ROOT_PAGE = "static/ghettorss-main-page.html"
DEFAULT_HTTP_PORT = 8000

def connect_to_database():
    db = sqlite3.connect(SQLITE_DATABASE)
    db.row_factory = sqlite3.Row
    return db

class GhettoRSSHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == '/':
            # serve up the base static page
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(open(ROOT_PAGE).read())
            return

        elif self.path.startswith('/post/'):
            # display a post
            post_id = self.path.lstrip("/post/")
            try:
                post_id = int(post_id)
            except ValueError:
                self.send_response(404)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write("Invalid post ID")
                return
            db = connect_to_database()
            cursor = db.cursor()
            cursor.execute("SELECT data FROM posts WHERE id=?", (post_id,))
            rows = cursor.fetchall()
            cursor.execute("UPDATE posts set read=1 WHERE id=?", (post_id,))
            db.commit()
            db.close()

            if len(rows) == 0:
                self.send_response(404)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write("Invalid post number")
                return
            post = rows[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(post['data'].encode('ascii', 'replace'))

        elif self.path.startswith('/file/'):
            # send a supporting file
            file_id = self.path.lstrip("/file/")
            try:
                file_id = int(file_id)
            except ValueError:
                self.send_response(404)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write("Invalid file ID (%s)" % (file_id))
                return
            db = connect_to_database()
            cursor = db.cursor()
            cursor.execute("SELECT content_type, data FROM files WHERE id=?", (file_id,))
            rows = cursor.fetchall()
            db.close()

            if len(rows) == 0:
                self.send_response(404)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write("Invalid file ID (%s)" % (file_id))
                return
            file_row = rows[0]
            self.send_response(200)
            self.send_header("Content-type", file_row['content_type'])
            self.end_headers()
            self.wfile.write(file_row['data'])

        elif self.path.startswith(STATIC_DIR):
            # serve something from the static directory
            filename = self.path.lstrip('/')
            if not os.path.exists(filename):
                self.send_response(404)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write("File '%s' does not exist" % (filename))
            else:
                # default content type is plaintext
                content_type = "text/plain"
                if filename.endswith(".html"):
                    content_type = "text/html"
                elif filename.endswith(".js"):
                    content_type = "application/javascript"
                elif filename.endswith(".css"):
                    content_type = "text/css"
                self.send_response(200)
                self.send_header("Content-type", content_type)
                self.end_headers()
                self.wfile.write(open(filename).read())

        elif self.path.startswith('/json/feeds'):
            # serve a JSON data structure with the index of feeds
            db = connect_to_database()
            cursor = db.cursor()
            cursor.execute("""
                SELECT
                    feeds.id AS feed_id,
                    feeds.title AS feed_title,
                    COUNT(feeds.id) AS unread_count
                FROM feeds
                INNER JOIN posts
                ON posts.feed_id=feeds.id
                GROUP BY feeds.id
            """)
            # There must be a more elegant way to convert this
            # SQLite result set into a JSON array but the JSON
            # module can't work directly with the SQLite data.
            # Thus, manually convert to an intermediate Python
            # data structure.
            rows = cursor.fetchall()
            feeds = []
            for row in rows:
                feed = {}
                for key in row.keys():
                    feed[key] = row[key]
                feeds.append(feed)
            db.close()
            feedset = {}
            feedset['ResultSet'] = feeds

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(json.dumps(feedset, sort_keys=True, indent=4))

        elif self.path.startswith('/json/feed/'):
            # serve a JSON data structure with the contents of 1 feed
            feed_id = self.path.lstrip("/json/feed/")
            try:
                feed_id = int(feed_id)
            except ValueError:
                self.send_response(404)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write("Invalid feed number")
                return
            db = connect_to_database()
            cursor = db.cursor()
            cursor.execute("""
                SELECT
                    id AS post_id, title, author, date, timestamp, read
                FROM posts
                WHERE feed_id=?
            """, (feed_id,))
            # SQLite -> Python data structure, so that easy JSON
            # serialization is possible later
            rows = cursor.fetchall()
            posts = []
            for row in rows:
                post = {}
                for key in row.keys():
                    post[key] = row[key]
                posts.append(post)
            db.close()
            postset = {}
            postset['ResultSet'] = posts

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(json.dumps(postset, sort_keys=True, indent=4))

        else:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write("Path '%s' does not exist" % (self.path))

def run(port,
        server_class=BaseHTTPServer.HTTPServer,
        handler_class=GhettoRSSHandler):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print "GhettoRSS server running on port %d... (Ctrl-C to exit)" % (port)
    httpd.serve_forever()


def usage():
    print """USAGE: ghettorss-server.py <options>
  -h, --help: Print this message
  -p, --port=[number]: Port on which to run the HTTP server
"""

if __name__ == '__main__':

    port = DEFAULT_HTTP_PORT
    # process command line arguments
    opts, args = getopt.getopt(sys.argv[1:], "hp:", ["help", "port="])

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-p", "--port"):
            try:
                port = int(arg)
            except ValueError:
                print "Invalid port number"
                sys.exit()

    # kick off the server
    run(port)
