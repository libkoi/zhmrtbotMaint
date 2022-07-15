# Some code snippets inspired by tool-phab-ban
# https://phabricator.wikimedia.org/source/tool-phab-ban
import os
import re
import json
import subprocess
import flask
from mwoauth import ConsumerToken, Handshaker, functions
from secret import customer_token, secret_token, flask_seckey


app = flask.Flask(__name__)
app.secret_key = flask_seckey
MW_URL = "https://meta.wikimedia.org/w/index.php"
HOME_PATH = "/data/project/zhmrtbot"
BASH_PATH = "bin/zhmrtbot.sh"
FILE_DIR = "public_html/file"

os.chdir(os.path.dirname(os.path.abspath(__file__)))

consumer_token = ConsumerToken(customer_token, secret_token)
handshaker = Handshaker(MW_URL, consumer_token)


def is_trusted(_user: str):
    ACL = {}
    with open("user.json", "r", encoding="utf-8") as f:
        ACL = json.load(f)
    return _user in ACL["trusted"]

@app.route('/')
def hello():
    return "<h1>200</h1>"

@app.route("/file/<name>")
def show(name: str):
    return flask.send_from_directory(f"{HOME_PATH}/{FILE_DIR}", name, mimetype="image/jpeg")

@app.route("/admin", methods=["GET"])
def portal():
    user = flask.session.get("u", None)
    return flask.render_template("index.html", user=user)

@app.route("/delete", methods=["POST"])
def delete():
    user = flask.session.get("u", None)
    if not user:
        return flask.redirect(flask.url_for("portal"))
    if not is_trusted(user):
        return flask.redirect(flask.url_for("denied"))
    file_name = flask.request.form["file"].strip()
    if(not re.match(r"^[a-zA-Z0-9\.]*$", file_name) or re.match(r"^\.*$", file_name)):
        flask.flash("Illegal input", "danger")
        return flask.redirect(flask.url_for("portal"))
    with subprocess.Popen(["rm", f"{HOME_PATH}/{FILE_DIR}/{file_name}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        err = process.stderr.read().decode("utf-8")
        if err == "":
            flask.flash(f'Deleted file "{file_name}"', "success")
            return flask.redirect(flask.url_for("portal"))
        flask.flash(err, "danger")
        return flask.redirect(flask.url_for("portal"))

@app.route("/status", methods=["POST"])
def status():
    user = flask.session.get("u", None)
    if not user:
        return flask.redirect(flask.url_for("portal"))
    if not is_trusted(user):
        return flask.redirect(flask.url_for("denied"))
    todo = flask.request.form["type"]
    if todo == "query":
        with subprocess.Popen([f"{HOME_PATH}/{BASH_PATH}", "status"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            out = process.stdout.read().decode("utf-8")
            err = process.stderr.read().decode("utf-8")
            if err == "":
                return flask.render_template("status.html", out=out)
            return flask.render_template("status.html", out=out, err=err)
    elif todo == "restart":
        with subprocess.Popen([f"{HOME_PATH}/{BASH_PATH}", "restart"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            out = process.stdout.read().decode("utf-8")
            err = process.stderr.read().decode("utf-8")
            if err == "":
                return flask.render_template("status.html", out=out)
            return flask.render_template("status.html", out=out, err=err)
    return flask.redirect(flask.url_for("portal"))

@app.route("/delete", methods=["GET"])
@app.route("/status", methods=["GET"])
def wrong_method():
    return flask.redirect(flask.url_for("portal"))

@app.route("/login")
def login():
    redirect, request_token = handshaker.initiate()
    flask.session["request_token_key"] = request_token.key
    flask.session["request_token_sec"] = request_token.secret
    return flask.redirect(redirect)

@app.route("/oauth-callback")
def callback():
    ver = flask.request.args.get("oauth_verifier")
    token = flask.request.args.get("oauth_token")
    request_token_key = flask.session.get("request_token_key", None)
    request_token_sec = flask.session.get("request_token_sec", None)
    if [x for x in (ver, token, request_token_key, request_token_sec) if x is None]:
        return flask.redirect(flask.url_for("portal"))
    response_qs = f"oauth_verifier={ver}&oauth_token={token}"
    # this is just a hack, NOT recommend
    request_token = functions.process_request_token(
        f"oauth_token={request_token_key}&oauth_token_secret={request_token_sec}")
    flask.session.clear()
    access_token = handshaker.complete(request_token, response_qs)
    ident = handshaker.identify(access_token)
    user = ident.get("username")
    flask.session["u"] = user
    if is_trusted(user):
        return flask.redirect(flask.url_for("portal"))
    return flask.redirect(flask.url_for("denied"))

@app.route("/logout")
def logout():
    flask.session.clear()
    return flask.redirect(flask.url_for("portal"))

@app.route("/403")
def denied():
    user = flask.session.get("u", None)
    flask.session.clear()
    if user:
        return flask.render_template("403.html", user=user)
    return flask.redirect(flask.url_for("portal"))
