# Some code snippets inspired by tool-phab-ban
# https://phabricator.wikimedia.org/source/tool-phab-ban
import functools
import os
import re
import json
import subprocess
from datetime import datetime
import flask
from flask_htmlmin import HTMLMIN
import requests
import urllib3
from mwoauth import ConsumerToken, Handshaker, functions
from secret import customer_token, secret_token


app = flask.Flask(__name__)
app.config["MINIFY_HTML"] = True
# "secret_key" is used by Flask for session feature.
# https://flask.palletsprojects.com/en/0.12.x/quickstart/#sessions
# https://stackoverflow.com/questions/34902378
app.secret_key = os.urandom(40).hex()
MW_URL = "https://meta.wikimedia.org/w/index.php"
MWOAUTH_UA = "zhmrtACL/1.0, tool-zhmrtbot, Toolforge"
HOME_PATH = "/data/project/zhmrtbot"
BASH_PATH = "bin/zhmrtbot.sh"
FILE_DIR = "public_html/file"
LOG_PATH = f"{HOME_PATH}/www/python/audit.log"

k8s_cert_path = f"{HOME_PATH}/.toolskube/client.crt"
k8s_key_path = f"{HOME_PATH}/.toolskube/client.key"
k8s_cert = (k8s_cert_path, k8s_key_path)
k8s_API_HOST = "https://k8s.svc.tools.eqiad1.wikimedia.cloud:6443"
k8s_NS = "tool-zhmrtbot"
k8s_zhmrtbot_name = "zhmrtbot.bot"


os.chdir(os.path.dirname(os.path.abspath(__file__)))
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
htmlmin = HTMLMIN(app)

consumer_token = ConsumerToken(customer_token, secret_token)
handshaker = Handshaker(MW_URL, consumer_token, user_agent=MWOAUTH_UA)


def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not flask.session.get("u", None):
            return flask.redirect(flask.url_for("portal"))
        return f(*args, **kwargs)
    return decorated_function

def trusted_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        ACL = {}
        with open("user.json", "r", encoding="utf-8") as fp:
            ACL = json.load(fp)
        user = flask.session.get("u", None)
        if not user in ACL["trusted"]:
            log_audit(f'"{user}" tried to perform a restricted action but failed.')
            return flask.redirect(flask.url_for("denied"))
        return f(*args, **kwargs)
    return decorated_function

def log_audit(msg):
    curts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    new = f'{curts} {msg}\n'
    if not os.path.isfile(LOG_PATH):
        with open(LOG_PATH, "w", encoding="utf-8") as fp:
            pass
    with open(LOG_PATH, "r+", encoding="utf-8") as fp:
        content = fp.read()
        fp.seek(0)
        fp.write(new + content)

# Several useful URLs:
# https://docs.okd.io/3.6/rest_api/kubernetes_v1.html
# https://kubernetes.io/docs/tasks/run-application/access-api-from-pod/
# https://kubernetes.io/docs/reference/access-authn-authz/authentication/
# https://stackoverflow.com/questions/47935675/
def k8s_get_pod_name():
    url_pods = f"{k8s_API_HOST}/api/v1/namespaces/{k8s_NS}/pods"
    pods_r = json.loads(requests.get(url_pods, cert=k8s_cert, verify=False).text)
    ret = []
    for pod in pods_r["items"]:
        if pod["metadata"]["labels"]["name"] == k8s_zhmrtbot_name:
            ret.append(pod["metadata"]["name"])
    return ret

def k8s_bot_status():
    bot_name_l = k8s_get_pod_name()
    ret = []
    if len(bot_name_l) == 1:
        bot_info = f"{k8s_API_HOST}/api/v1/namespaces/{k8s_NS}/pods/{bot_name_l[0]}"
        bot_info_r = json.loads(requests.get(bot_info, cert=k8s_cert, verify=False).text)
        ret.append(bot_info_r)
    if len(bot_name_l) > 1: # A pod is being terminated now!
        for bot in bot_name_l:
            bot_info = f"{k8s_API_HOST}/api/v1/namespaces/{k8s_NS}/pods/{bot}"
            bot_info_r = json.loads(requests.get(bot_info, cert=k8s_cert, verify=False).text)
            ret.append(bot_info_r)
    return ret

def k8s_bot_log():
    bot_name_l = k8s_get_pod_name()
    ret = ""
    if len(bot_name_l) == 1:
        bot_info = f"{k8s_API_HOST}/api/v1/namespaces/{k8s_NS}/pods/{bot_name_l[0]}/log"
        bot_info_r = requests.get(bot_info, cert=k8s_cert, verify=False).text
        # How to remove the ANSI escape sequences from a string
        # https://stackoverflow.com/questions/14693701/
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        ret = ansi_escape.sub("", bot_info_r)
    if ret == "":
        ret = None
    return ret

def k8s_pod_del():
    bot_name_l = k8s_get_pod_name()
    if len(bot_name_l) != 1:
        return -1
    url = f"{k8s_API_HOST}/api/v1/namespaces/{k8s_NS}/pods/{bot_name_l[0]}"
    requests.delete(url, cert=k8s_cert, verify=False)
    return 0


@app.route("/")
def hello():
    return "200"

@app.route("/file/<name>")
def show(name: str):
    return flask.send_from_directory(f"{HOME_PATH}/{FILE_DIR}", name, mimetype="image/jpeg")

@app.route("/admin", methods=["GET"])
def portal():
    user = flask.session.get("u", None)
    return flask.render_template("index.html", user=user)

@app.route("/delete", methods=["POST"])
@login_required
@trusted_required
def delete():
    user = flask.session.get("u", None)
    file_name = flask.request.form["file"].strip()
    if(not re.match(r"^[a-zA-Z0-9\.]*$", file_name) or re.match(r"^\.*$", file_name)):
        flask.flash("Illegal input", "danger")
        return flask.redirect(flask.url_for("portal"))
    with subprocess.Popen(["rm", f"{HOME_PATH}/{FILE_DIR}/{file_name}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        err = process.stderr.read().decode("utf-8")
        if err == "":
            flask.flash(f'Deleted file "{file_name}"', "success")
            log_audit(f'"{user}" deleted file "{file_name}"')
            return flask.redirect(flask.url_for("portal"))
        flask.flash(err, "danger")
        return flask.redirect(flask.url_for("portal"))

@app.route("/restart", methods=["POST"])
@login_required
@trusted_required
def bot_restart():
    user = flask.session.get("u", None)
    if not user:
        return flask.redirect(flask.url_for("portal"))
    todo = flask.request.form["type"]
    if todo == "restart":
        stat = k8s_pod_del()
        out = ""
        title = "Success"
        if stat == 0:
            log_audit(f'"{user}" restarted service "{k8s_zhmrtbot_name}"')
            out = "Request sent, please wait for at most one minute."
        else:
            out = "A pod is being terminated now, please try again later."
            title = "Failed"
        return flask.render_template("log.html", title=title, log=out)
    return flask.redirect(flask.url_for("portal"))

@app.route("/status")
@login_required
def bot_status():
    user = flask.session.get("u", None)
    if not user:
        return flask.redirect(flask.url_for("portal"))
    out = ""
    notice = ""
    out_dict_l = k8s_bot_status()
    if len(out_dict_l) == 1:
        out = json.dumps(out_dict_l[0], indent=4)
    if len(out_dict_l) > 1:
        for o in out_dict_l:
            out += json.dumps(o, indent=4)
        notice = "Warning: A pod is being terminated now!"
    if out == "":
        out = "An unknown error occured!"
    if notice == "":
        notice = None
    return flask.render_template("log.html", title="Status", log=out, notice=notice)

@app.route("/log")
@login_required
def bot_log():
    user = flask.session.get("u", None)
    if not user:
        return flask.redirect(flask.url_for("portal"))
    log = k8s_bot_log()
    if not log:
        log = "A pod is being terminated now, please try again later."
    return flask.render_template("log.html", title="Pod logs (UTC)", log=log)

@app.route("/audit")
@login_required
def audit():
    user = flask.session.get("u", None)
    if not user:
        return flask.redirect(flask.url_for("portal"))
    log = ""
    if not os.path.isfile(LOG_PATH):
        log = "No audit log found"
    else:
        with open(LOG_PATH, "r", encoding="utf-8") as fp:
            lcnt = len(fp.readlines())
            fp.seek(0)
            ll = [next(fp) for _ in range(min(lcnt, 50))]
            for l in ll:
                log += l
    return flask.render_template("log.html", title="Audit logs (UTC)", log=log)

@app.route("/delete", methods=["GET"])
@app.route("/restart", methods=["GET"])
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
        flask.session.clear()
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
    return flask.redirect(flask.url_for("portal"))

@app.route("/logout")
def logout():
    flask.session.clear()
    return flask.redirect(flask.url_for("portal"))

@app.route("/403")
@login_required
def denied():
    user = flask.session.get("u", None)
    return flask.render_template("403.html", user=user)

if __name__ == "__main__":
    app.run()
