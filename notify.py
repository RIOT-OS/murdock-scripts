#! /usr/bin/env python3
#
# Copyright (C) 2019 Freie Universitaet Berlin
#
# This file is subject to the terms and conditions of the GNU General Public
# License v3. See the file LICENSE in the top level directory for more details.

import argparse
import json
import logging
import os
import smtplib
import ssl
import sys
import toml

from bs4 import BeautifulSoup
from email.message import EmailMessage

from update_nightly_list import find_commit_build, FILENAME as NIGHTLIES_JSON

MURDOCK_CONFIG = os.environ.get("MURDOCK_CONFIG", "/etc/murdock.toml")
MESSAGE_TEMPLATES = {
    "passed": "Everything is fine.",
    "errored": """The following nightlies failed:

{error_list}
""",
}


class MailNotifier(object):
    SECURITY_CLASS = {
        "none": smtplib.SMTP,
        "starttls": smtplib.SMTP,
        "ssl": smtplib.SMTP_SSL,
    }

    def __init__(self, server, sender, receiver, port=0,
                 username=None, password=None,
                 security="none", *args, **kwargs):
        self.sender = sender
        self.receiver = receiver
        server_args = {"host": server, "port": port}
        if security in ["starttls", "ssl"]:
            context = ssl.create_default_context()
            if security == "ssl":
                server_args["context"] = context
        elif security not in MailNotifier.SECURITY_CLASS:
            raise ValueError("security must be in {}"
                             .format(MailNotifier.SECURITY_CLASS))
        else:
            context = None
        self.server = MailNotifier.SECURITY_CLASS[security](**server_args)
        if security == "starttls":
            self.server.ehlo()
            self.server.starttls(context=context)
        if username is not None and password is not None:
            self.server.ehlo()
            self.server.login(username, password)

    def __del__(self):
        self.server.quit()

    def notify(self, subject, message, *args, **kwargs):
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["To"] = self.receiver
        msg["From"] = self.sender
        msg["Content-Type"] = "text/plain"
        msg.set_content(message)
        self.server.send_message(msg)


def get_config():
    with open(MURDOCK_CONFIG) as config_file:
        return toml.load(config_file)["notifications"]


def notify_branch_results(notifiers, config, repodir, current_build,
                          last_build=None, branch="master"):
    nightlies_json = os.path.join(repodir, branch, NIGHTLIES_JSON)
    if not os.path.exists(nightlies_json):
        logging.warning("{} not found".format(nightlies_json))
        return
    with open(nightlies_json) as f:
        nightlies = json.load(f)
    current_build = find_commit_build(nightlies, current_build)
    if last_build is not None:
        last_build = find_commit_build(nightlies, last_build)
    if config.get("only_changes") and (last_build is not None) and \
            (last_build["result"] == current_build["result"]):
        logging.info("Skipping unchanged status for {} to {}"
                     .format(last_build["commit"], current_build["commit"]))
        return
    current_build["commit_short"] = current_build["commit"][:7]
    current_build["branch"] = branch
    result = current_build["result"]
    subject = "Nightly build on {branch} for {commit_short} {result}" \
              .format(**current_build)
    summary = {}
    if result == "errored":
        output_html = os.path.join(repodir, branch,
                                   current_build["commit"], "output.html")
        if not os.path.exists(output_html):
            logging.error("{} does not exist".format(output_html))
            sys.exit(1)
        with open(output_html) as html:
            soup = BeautifulSoup(html, "html.parser")
            error = soup.find("a", attrs={"name": "error0"})
            error_list = []
            if error is None:
                logging.warning("{} has no error list".format(output_html))
            else:
                while error.next_sibling is not None and \
                      (error.next_sibling.name == "a" or
                       error.next_sibling.string.strip() == ""):
                    error = error.next_sibling
                    if error.string.strip() == "":
                        continue
                    error_list.append(" - {}".format(error.string.strip()))
            summary["error_list"] = "\n".join(error_list)
    for notifier in notifiers:
        notifier.notify(subject, MESSAGE_TEMPLATES[result].format(**summary))


def notify_results(notifiers, config, repodir, current_build,
                   last_build=None):
    branches = config["branches"]
    for branch in branches:
        notify_branch_results(notifiers, config, repodir, current_build,
                              last_build, branch)


def main(repodir, current_build, last_build=None):
    NOTIFIER_CLASS = {
            "mail": MailNotifier
        }
    try:
        config = get_config()
    except FileNotFoundError:
        logging.critical("Murdock config {} not found.".format(MURDOCK_CONFIG))
        logging.error("You can change the path to the Murdock config using "
                      "the MURDOCK_CONFIG environment variable")
        sys.exit(1)
    except KeyError:
        logging.error("Config has no 'notifications' section")
        sys.exit(1)
    notifiers = []
    for notifier, notifier_config in config.items():
        if notifier in ["branches", "only_changes"]:
            continue
        try:
            notifier_class = NOTIFIER_CLASS[notifier]
        except KeyError:
            logging.warning("Notifier class {} is not provided"
                            .format(notifier))
            sys.exit(1)
        notifiers.append(notifier_class(**notifier_config))
    notify_results(notifiers, config, repodir, current_build,
                   last_build)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("repodir", help="Path to the current build")
    p.add_argument("current_build", help="commit hash of current build")
    p.add_argument("last_build", help="commit hash of last build", nargs="?")
    args = p.parse_args()
    main(**vars(args))
