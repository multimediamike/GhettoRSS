GhettoRSS is an offline RSS reader. Actually, that's not entirely accurate.
GhettoRSS is what most users expect from an offline RSS reader. Offline RSS
readers download and cache RSS feeds for later, disconnected reading.
However, RSS feeds often don't contain the useful information.

GhettoRSS makes an effort to follow links in RSS feeds and download full
content behind the links, including supporting images and CSS files and
stores them in a local database. A custom web server run locally allows you
to browse the content using the web browser of your choice.


Software
========
GhettoRSS is written in Python and relies almost entirely on Python standard
library components. The one additional library it requires is FeedParser,
developed here:

  http://code.google.com/p/feedparser/

In Ubuntu Linux, this can be installed through the package manager via:

  apt-get install python-feedparser


Usage
=====
There are 3 main files is play:

* ghetto-feeds.txt
* ghettorss-update.py
* ghettorss-server.py

ghetto-feeds.txt lists one RSS feed per line. Lines beginning with '#' are
considered comments and ignored. E.g.:

# this is a comment; ignored
feed://xkcd.com/rss.xml
http://feeds.feedburner.com/codinghorror/

When connected to the internet, run ghettorss-update.py to query each RSS
feed for updates.

To browse the feeds, run ghettorss-server.py. At this point, the machine will
be listening for web browser connections on port 8000 (a different port
number can be specified using -p or --port). Thus, point your web browser to:

  http://localhost:8000/

And start reading your RSS feeds.


Author
======
Mike Melanson (mike -at- multimedia.cx)
