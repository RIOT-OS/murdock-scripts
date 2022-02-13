import argparse
import asyncio
import os
import sys
from email.message import EmailMessage
from typing import List, Optional

import aiosmtplib
import httpx
import yaml

from pydantic import BaseModel, error_wrappers


CONFIGFILE_DEFAULT = os.path.join(os.path.dirname(__file__), "config.yml")


class MailConfig(BaseModel):
    mailto: str
    server: str
    port: int
    use_tls: bool
    username: str
    password: str


class NotifyConfig(BaseModel):
    api_url: Optional[str] = "http://localhost:8000"
    mail: Optional[MailConfig]


class MailNotifier:
    def __init__(self, config: MailConfig):
        self.mailto = config.mailto
        self.server = config.server
        self.port = config.port
        self.use_tls = config.use_tls
        self.username = config.username
        self.password = config.password

    async def notify(self, title: str, content: str):
        message = EmailMessage()
        message["From"] = "ci@riot-os.org"
        message["To"] = self.mailto
        message["Subject"] = title
        message.set_content(content)

        try:
            await aiosmtplib.send(
                message,
                hostname=self.server,
                port=self.port,
                use_tls=self.use_tls,
                username=self.username,
                password=self.password,
            )
        except aiosmtplib.errors.SMTPAuthenticationError as exc:
            print(f"Cannot send email: {exc}")
        print("Notification email sent")


async def fetch_finished_jobs(
    branch, api_url: str, limit: Optional[int] = 5
) -> List[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{api_url}/jobs/finished?limit={limit}&is_branch=1&branch={branch}",
            headers={
                "Accept": "application/json",
            },
        )
        if response.status_code != 200:
            sys.exit(1)

        return response.json()


def parse_config_file(config_filename: str) -> NotifyConfig:
    with open(config_filename) as config_file:
        content = config_file.read()
    try:
        config = yaml.load(content, Loader=yaml.FullLoader)
    except yaml.YAMLError as exc:
        print(f"Invalid yml config file: {exc}")
        sys.exit(1)

    try:
        return NotifyConfig(**config)
    except error_wrappers.ValidationError as exc:
        print(
            "Missing server configuration field:\n"
            f"{error_wrappers.display_errors(exc.errors())}"
        )
        sys.exit(1)


NOTIFIERS = {
    "mail": MailNotifier,
}


async def notify(branch: str, job_uid: str, job_result: int, configfile: str):
    config = parse_config_file(configfile)
    finished_jobs = await fetch_finished_jobs(branch, config.api_url)

    job_state = "passed" if int(job_result) == 0 else "errored"
    if finished_jobs and finished_jobs[0]["state"] == job_state:
        print(f"No result change for branch '{branch}', don't notify")
        return

    title = f"Murdock job {job_state}: {branch}"
    content = f"""Murdock job {job_uid} {job_state}!

Results: {config.api_url}/results/{job_uid}
    """

    for notifier_type, notifier_cls in NOTIFIERS.items():
        notifier = notifier_cls(getattr(config, notifier_type))
        await notifier.notify(title, content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "branch", type=str, help="Name of the branch to notify results from"
    )
    parser.add_argument("--job-uid", type=str, help="UID of the Murdock job")
    parser.add_argument("--job-result", type=int, help="Result of the Murdock job")
    parser.add_argument(
        "-f",
        "--configfile",
        type=str,
        default=CONFIGFILE_DEFAULT,
        help="SMTP configuration file",
    )
    args = parser.parse_args()
    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(notify(**vars(args)))


if __name__ == "__main__":
    main()
