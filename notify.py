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


class MailNotifier(BaseModel):
    mailto: List[str]
    server: str
    port: int
    use_tls: bool
    username: str
    password: str

    async def notify(self, title: str, content: str):
        message = EmailMessage()
        message["From"] = "ci@riot-os.org"
        message["To"] = ";".join(self.mailto)
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


class NotifiersModel(BaseModel):
    mail: Optional[MailNotifier]


class NotifyConfig(BaseModel):
    murdock_url: Optional[str] = "http://localhost:8000"
    api_url: Optional[str] = "http://localhost:8000"
    notifiers: NotifiersModel


async def fetch_running_job(uid, api_url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{api_url}/job/{uid}",
            headers={
                "Accept": "application/json",
            },
        )
        if response.status_code != 200:
            print(f"Running job with uid '{uid}' not found, aborting")
            sys.exit(1)

        return response.json()


async def fetch_finished_jobs(branch, api_url: str) -> List[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{api_url}/jobs/finished?limit=1&is_branch=1&branch={branch}",
            headers={
                "Accept": "application/json",
            },
        )
        if response.status_code != 200:
            return None

        return response.json()[0]


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


async def notify(branch: str, job_uid: str, configfile: str):
    config = parse_config_file(configfile)
    running_job = await fetch_running_job(job_uid, config.api_url)
    last_matching_job = await fetch_finished_jobs(branch, config.api_url)

    if (
        "status" in running_job
        and "failed" in running_job["status"]
        and int(running_job["status"]["failed"]) == 0
    ):
        job_state = "passed"
    else:
        job_state = "errored"

    if (
        last_matching_job is not None
        and last_matching_job["state"] == job_state
        and job_state == "passed"
    ):
        print(f"Job for branch '{branch}' still successful, don't notify")
        return

    title = f"Murdock job {job_state}: {branch}"
    content = f"""Murdock job for branch '{branch}' {job_state}!

Results: {config.murdock_url}/details/{job_uid}
    """

    for _, notifier in config.notifiers:
        await notifier.notify(title, content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "branch", type=str, help="Name of the branch"
    )
    parser.add_argument("--job-uid", type=str, help="UID of the Murdock job")
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
