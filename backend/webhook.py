"""
FaceFind Auto-Deploy Webhook
Listens for GitHub push events and auto-pulls + restarts the service.

Setup:
  1. Run this on your droplet as a systemd service
  2. Add a webhook in GitHub repo settings pointing to:
     https://facefind.maheshwar.tech/api/deploy/webhook
"""
import os
import hmac
import hashlib
import subprocess
import logging
from fastapi import APIRouter, Request, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# Set this in .env — must match the "Secret" in GitHub webhook settings
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PROJECT_DIR = "/var/www/facefind"


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not WEBHOOK_SECRET:
        return True  # Skip verification if no secret configured

    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/api/deploy/webhook")
async def github_webhook(request: Request):
    """
    Receives GitHub push webhook → git pull → rebuild frontend → restart service.
    """
    body = await request.body()

    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if WEBHOOK_SECRET and not verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Check it's a push event
    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return {"status": "pong"}

    if event != "push":
        return {"status": "ignored", "event": event}

    # Run deploy commands
    try:
        commands = [
            f"cd {PROJECT_DIR} && git pull origin main",
            f"cd {PROJECT_DIR}/frontend && npm run build",
            "sudo systemctl restart facefind",
        ]

        results = []
        for cmd in commands:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=120
            )
            results.append({
                "command": cmd.split("&&")[-1].strip(),
                "status": "ok" if result.returncode == 0 else "error",
                "output": result.stdout[-200:] if result.stdout else "",
            })
            if result.returncode != 0:
                logger.error(f"Deploy command failed: {cmd}\n{result.stderr}")
                break

        logger.info("✅ Auto-deploy completed")
        return {"status": "deployed", "results": results}

    except Exception as e:
        logger.error(f"Auto-deploy failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
