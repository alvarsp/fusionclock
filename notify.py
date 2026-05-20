import logging

import requests

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config):
        self.config = config

    def send(self, message: str):
        logger.info("Notification: %s", message)
        if self.config.notify_webhook:
            self._post_webhook(message)

    def _post_webhook(self, message: str):
        try:
            # Slack-compatible payload; also works with Discord and most webhooks
            requests.post(
                self.config.notify_webhook,
                json={"text": message},
                timeout=10,
            ).raise_for_status()
        except Exception as exc:
            logger.warning("Webhook failed: %s", exc)
