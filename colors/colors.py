#!/usr/bin/env python

import datetime
import functools
import logging
import os
import random
import signal
import time

__version__ = "1.4"
PORT=5000
HOSTNAME=os.getenv("HOSTNAME")

from flask import Flask, jsonify, request, Response
app = Flask(__name__)


######## Colors storage
#
# Yeah, this is not the most efficient way to do this, but it's quick a quickie demo for the PoC
# I could either use a real database backend, or set up a class to store each record.

colors = [
  {"name":"black",	 "fg_code": 30, "bg_code": 40},
  {"name":"red",	 "fg_code": 31,	"bg_code": 41},
  {"name":"green",	 "fg_code": 32,	"bg_code": 42},
  {"name":"yellow",	 "fg_code": 33,	"bg_code": 43},
  {"name":"blue",	 "fg_code": 34,	"bg_code": 44},
  {"name":"magenta", "fg_code": 35,	"bg_code": 45},
  {"name":"cyan",	 "fg_code": 36,	"bg_code": 46},
  {"name":"white",	 "fg_code": 37,	"bg_code": 47}
]

######## Utilities

class RichStatus (object):
    def __init__(self, ok, **kwargs):
        self.ok = ok
        self.info = kwargs
        self.info['hostname'] = HOSTNAME
        self.info['time'] = datetime.datetime.now().isoformat()
        self.info['version'] = __version__

    # Remember that __getattr__ is called only as a last resort if the key
    # isn't a normal attr.
    def __getattr__(self, key):
        return self.info.get(key)

    def __bool__(self):
        return self.ok

    def __nonzero__(self):
        return bool(self)

    def __contains__(self, key):
        return key in self.info

    def __str__(self):
        attrs = ["%s=%s" % (key, self.info[key]) for key in sorted(self.info.keys())]
        astr = " ".join(attrs)

        if astr:
            astr = " " + astr

        return "<RichStatus %s%s>" % ("OK" if self else "BAD", astr)

    def toDict(self):
        d = { 'ok': self.ok }

        for key in self.info.keys():
            d[key] = self.info[key]

        return d

    @classmethod
    def fromError(self, error, **kwargs):
        kwargs['error'] = error
        return RichStatus(False, **kwargs)

    @classmethod
    def OK(self, **kwargs):
        return RichStatus(True, **kwargs)

def standard_handler(f):
    func_name = getattr(f, '__name__', '<anonymous>')

    @functools.wraps(f)
    def wrapper(*args, **kwds):
        rc = RichStatus.fromError("impossible error")
        session = request.headers.get('x-colors-session', None)
        username = request.headers.get('x-authenticated-as', None)

        logging.debug("%s %s: session %s, username %s, handler %s" %
                      (request.method, request.path, session, username, func_name))

        try:
            rc = f(*args, **kwds)
        except Exception as e:
            logging.exception(e)
            rc = RichStatus.fromError("%s: %s %s failed: %s" % (func_name, request.method, request.path, e))

        code = 200

        # This, candidly, is a bit of a hack.

        if session:
            rc.info['session'] = session

        if username:
            rc.info['username'] = username

        if not rc:
            if 'status_code' in rc:
                code = rc.status_code
            else:
                code = 500

        resp = jsonify(rc.toDict())
        resp.status_code = code

        if session:
            resp.headers['x-colors-session'] = session

        return resp

    return wrapper

def in_dict(d, k):
    for i in d:
        for key, value in i.iteritems():
             if key == 'name':
                 return value

######## REST endpoints

####
# GET /health does a basic health check. It always returns a status of 200
# with an empty body.

@app.route("/health", methods=["GET", "HEAD"])
@standard_handler
def health():
    return RichStatus.OK(msg="colors health check OK")

####
# GET / returns a random color as the 'color' element of a JSON dictionary. It
# always returns a status of 200.

@app.route("/", methods=["GET"])
@standard_handler
def statement():
    idx = random.choice(range(len(colors)))
    color = colors[idx]
    return RichStatus.OK(idx=idx, color=color["name"])

####
# GET /<color_str> returns a specific color. 'color_str' is the string name
# of the color in our array above.
#
# - If all goes well, it returns a JSON dictionary with the requested color as
#   the 'color' element, with status 200.
# - If something goes wrong, it returns a JSON dictionary with an explanation
#   of what happened as the 'error' element, with status 400.
#

@app.route("/<string:name>", methods=["GET"])
@standard_handler
def specific_color(name):
    idx = next((index for (index, d) in enumerate(colors) if d["name"] == name), None)
    if idx is None:
        return RichStatus.fromError("no color %s" % name, status_code=400)

    return RichStatus.OK(color=colors[idx])


####
# GET /<color_str>/bg returns a the bg_code of the requested color_str.
#

@app.route("/<string:name>/bg", methods=["GET"])
@standard_handler
def color_bg(name):
    idx = next((index for (index, d) in enumerate(colors) if d["name"] == name), None)
    if idx is None:
        return RichStatus.fromError("no color %s" % name, status_code=400)

    return RichStatus.OK(color=colors[idx]["name"], path=request.path.rsplit('/', 1)[-1], fg=colors[idx]["bg_code"])


####
# GET /<color_str>/fg returns a the fg_code of the requested color_str.
#

@app.route("/<string:name>/fg", methods=["GET"])
@standard_handler
def color_fg(name):
    idx = next((index for (index, d) in enumerate(colors) if d["name"] == name), None)
    if idx is None:
        return RichStatus.fromError("no color %s" % name, status_code=400)

    return RichStatus.OK(color=colors[idx]["name"], path=request.path.rsplit('/', 1)[-1], fg=colors[idx]["fg_code"])


@app.route("/crash", methods=["GET"])
@standard_handler
def crash():
    logging.warning("dying in 1 seconds")
    time.sleep(1)
    os.kill(os.getpid(), signal.SIGTERM)
    time.sleep(1)
    os.kill(os.getpid(), signal.SIGKILL)

######## Mainline

def main():
    app.run(debug=True, host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    logging.basicConfig(
        # filename=logPath,
        level=logging.DEBUG, # if appDebug else logging.INFO,
        format="%%(asctime)s colors %s %%(levelname)s: %%(message)s" % __version__,
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    logging.info("initializing on %s:%d" % (HOSTNAME, PORT))
    main()
