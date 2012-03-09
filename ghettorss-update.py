#!/usr/bin/python

# ghettorss-update.py
# part of GhettoRSS by Mike Melanson (mike -at- multimedia.cx)

import feedparser
import hashlib
import HTMLParser
import httplib
import sqlite3
import sys
import urlparse

FEEDS_FILE = "ghetto-feeds.txt"
SQLITE_DATABASE = "ghettorss.sqlite3"

def connect_to_database():
    db = sqlite3.connect(SQLITE_DATABASE)
    db.row_factory = sqlite3.Row
    return db

# initialize the database as necessary
def init_database():
    db = connect_to_database()
    db.execute("""
        CREATE TABLE IF NOT EXISTS feeds
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            feed_url TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS posts
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER,
            title TEXT,
            author TEXT,
            link TEXT,
            date TEXT,
            timestamp INTEGER,
            fetched INTEGER DEFAULT 0,
            read INTEGER DEFAULT 0,
            data TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS files
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER,
            hash TEXT,
            content_type TEXT,
            data TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS post_file_link
        (
            post_id INTEGER,
            file_id INTEGER
        )
    """)
    db.commit()
    db.close()


# This parser only seeks out <img> tags and references to CSS files. 
# Thanks to this blog post for the tutorial:
#   http://unethicalblogger.com/node/180
class ImgCssParser(HTMLParser.HTMLParser):

    def __init__(self, cursor, post_id, server, url_path):
        HTMLParser.HTMLParser.__init__(self)
        self.cursor = cursor
        self.post_id = post_id
        self.server = server
        self.url_path = url_path
        self.stack = []

    # Fetch the link (figure out the path as necessary), store in the database
    # if it's not already there, and return the file ID.
    def fetch_file(self, link):
        file_id = -1
        link_parse = urlparse.urlparse(link)
        server = link_parse[1]
        if server == "":
            server = self.server
        path = link_parse[2]
        print "    Fetching supporting file @ %s%s" % (server, path)
        conn = httplib.HTTPConnection(server)
        conn.request("GET", path, None, {})
        network_data = None
        try:
            response = conn.getresponse()
            if (response.status == 200):
                content_type = response.getheader("Content-type")
                network_data = response.read()
            conn.close()
        except ValueError:
            print "  **** Caught a ValueError while fetching %s%s" % (server, base_url)
        if network_data == None:
            print "could not fetch %s" % (link)
        else:
            sha_hash = hashlib.sha256(network_data).hexdigest()

            # check if the file hash already lives in database
            self.cursor.execute("SELECT id, hash FROM files WHERE hash=?", (sha_hash,))
            rows = self.cursor.fetchall()
            if len(rows) == 0:
                # insert new file
                self.cursor.execute("INSERT INTO files VALUES(NULL, ?, ?, ?, ?)",
                    (self.post_id, sha_hash, content_type, sqlite3.Binary(network_data)))
                self.cursor.execute("SELECT id, hash FROM files WHERE hash=?", (sha_hash,))
                rows = self.cursor.fetchall()
                if len(rows) == 0:
                    print "failed to insert file"
                else:
                    file_id = rows[0]['id']
            else:
                # use existing file id
                file_id = rows[0]['id']

            # establish a correlation between the post and the file for bookkeeping
            if file_id != -1:
                self.cursor.execute("SELECT * FROM post_file_link WHERE post_id=? AND file_id=?", (self.post_id, file_id))
                if len(self.cursor.fetchall()) == 0:
                    self.cursor.execute("INSERT INTO post_file_link VALUES(?, ?)", (self.post_id, file_id))

        return file_id

    def handle_file(self, tag, attrs):
        fetch_link = 0
        link = ""
        mod_index = -1  # the attribute index that will need to be modified later

        if tag == "link":
            for i in xrange(len(attrs)):
                (k, v) = attrs[i]
                if k == "rel" and v == "stylesheet":
                    fetch_link = 1
                if k == "href":
                    mod_index = i
                    link = v
            if fetch_link:
                file_id = self.fetch_file(link)
                attrs[mod_index] = ("href", "/file/%d" % (file_id))

        if tag == "img":
            for i in xrange(len(attrs)):
                (k, v) = attrs[i]
                if k == "src":
                    mod_index = i
                    fetch_link = 1
                    link = v
            if fetch_link:
                file_id = self.fetch_file(link)
                attrs[mod_index] = ("src", "/file/%d" % (file_id))


    def handle_starttag(self, tag, attrs):
        self.handle_file(tag, attrs)
        self.stack.append(unicode(self.__html_start_tag(tag, attrs)))


    def handle_startendtag(self, tag, attrs):
        self.handle_file(tag, attrs)
        self.stack.append(unicode(self.__html_startend_tag(tag, attrs)))


    def handle_endtag(self, tag):
        self.stack.append(unicode(self.__html_end_tag(tag)))


    def handle_data(self, data):
        self.stack.append(unicode(data, errors='replace'))


    def __html_start_tag(self, tag, attrs):
        return '<%s%s>' % (tag, self.__html_attrs(attrs))


    def __html_startend_tag(self, tag, attrs):
        return '<%s%s/>' % (tag, self.__html_attrs(attrs))


    def __html_end_tag(self, tag):
        return '</%s>' % (tag)


    def __html_attrs(self, attrs):
        _attrs = ''
        if attrs:
            _attrs = ' %s' % (' '.join(('%s="%s"') % attr for attr in attrs))
        return _attrs


    def get_new_page(self):
        page = ''.join(self.stack)
        return page


# given a db cursor, feed ID, and RSS entry dictionary, download the page,
# parse the HTML, download any supporting files, and store them all in
# the database
def fetch_post(cursor, feed_id, entry):
    if "title" in entry:
        title = entry['title']
    else:
        title = "(no title)"
    if "author" in entry:
        author = entry['author']
    else:
        author = "(unknown)"
    link = entry['link']
    date = entry['updated']
    # TODO: need to convert this data structure into a proper Unix timestamp
    timestamp = entry['updated_parsed']
    cursor.execute("SELECT id FROM posts WHERE feed_id=? AND title=? AND date=?", (feed_id, title, date))
    rowcount = len(cursor.fetchall())
    if rowcount == 0:
        cursor.execute("""
            INSERT INTO posts 
            VALUES (NULL, ?, ?, ?, ?, ?, ?, 0, 0, NULL)
        """, (feed_id, title, author, link, date, 0))

    cursor.execute("SELECT id, fetched FROM posts WHERE feed_id=? AND title=? AND date=?", (feed_id, title, date))
    rows = cursor.fetchall()
    if len(rows) == 0:
        print "failed to enter post '%s'" % (title)
        sys.exit(2)
    post_id = rows[0]['id']
    fetched = rows[0]['fetched']

    # time to fetch the page and all its parts
    link_parse = urlparse.urlparse(link)
    server = link_parse[1]
    base_url = link_parse[2]
    if not fetched:
        # fetch the page
        try:
            print "  Fetching post \"%s\"" % (title)
            conn = httplib.HTTPConnection(server)
            conn.request("GET", base_url, None, {})
            network_data = None
            response = conn.getresponse()
            if (response.status == 200):
                network_data = response.read()
            conn.close()
            if network_data <> None:
                # parse the page and download supporting files
                parser = ImgCssParser(cursor, post_id, server, base_url)
                parser.feed(network_data)
                page = parser.get_new_page()
                cursor.execute("UPDATE posts SET fetched=1, data=? WHERE id=?", (page, post_id))

        except ValueError:
            print "  **** Caught a ValueError while fetching %s%s" % (server, base_url)
        except:
            print "  Failed."


def process_feed(original_feed):
    # feed:// -> http://
    feed = original_feed
    if (feed.startswith("feed://")):
        feed = "http" + feed.lstrip("feed")

    rss = feedparser.parse(feed)
    title = rss['feed']['title']
    print "Updated feed \"%s\"" % (title)

    db = connect_to_database()
    cursor = db.cursor()

    # check if title exists in feed table; if not,
    # add a new row with the title and feed URL
    cursor.execute("SELECT id FROM feeds WHERE title=? AND feed_url=?", (title, feed))
    rowcount = len(cursor.fetchall())
    if rowcount == 0:
        db.execute("""
            INSERT INTO feeds
            VALUES (NULL, ?, ?)
        """, (title, feed))

    # fetch the ID corresponding to the feed
    cursor.execute("SELECT id FROM feeds WHERE title=? AND feed_url=?", (title, feed))
    rows = cursor.fetchall()
    if len(rows) == 0:
        print "Failed to insert feed %s (%s)" % (title, feed)
        sys.exit(1)
    feed_id = rows[0]['id']

    # iterate through each entry in the feed
    # look for a row in the posts table that matches the feed id,
    # title, and date; if nothing exists, proceed to add it
    for i in xrange(len(rss['entries'])):
        fetch_post(cursor, feed_id, rss['entries'][i])

    # finish
    db.commit()
    db.close()


# main program entry point
init_database()
try:
    feeds = open(FEEDS_FILE).read().splitlines()
except IOError:
    print "Error: Can not find 'ghetto-feeds.txt' file with RSS feed"
    sys.exit(1)
for feed in feeds:
    if feed.startswith('#'):
        continue
    if feed == "":
        continue
    process_feed(feed)

