"""Test-mode subscription checkout/inbox. It never enables customer calls or paid minutes.

Funding history is separate from V1's immutable test entitlement. No monthly reset,
payment-success browser callback, or signed unknown subscription grants runtime access.
"""

import hashlib
import hmac
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import Settings
from app.models.db.voice_lifecycle import VoiceBillingReceipt, VoiceFundingPeriod, VoiceSubscription
from app.voice.events import _pairs
from app.voice.service import VoiceSessionService


def test_gate(settings: Settings) -> None:
    if (
        not settings.voice_billing_test_enabled
        or settings.environment not in ("development", "staging")
        or not settings.razorpay_test_key_id.startswith("rzp_test_")
        or not settings.razorpay_test_key_secret.get_secret_value()
        or not re.fullmatch(r"plan_[A-Za-z0-9]{1,100}", settings.voice_test_plan_id)
        or settings.voice_test_plan_seconds < 1
    ):
        raise HTTPException(503, "Subscription test mode is unavailable.")


class TestBillingService(VoiceSessionService):
    __test__ = False

    async def checkout(
        self, owner: uuid.UUID, key: uuid.UUID, client: httpx.AsyncClient | None = None
    ) -> dict[str, Any]:
        test_gate(self.settings)
        if not self.test_access(owner):
            raise HTTPException(403, "Subscription testing is limited to development identities.")
        async with self.factory() as db:
            await self._ensure(db, owner, await self.now(db))
            await self.lock_entitlement(db, owner)
            prior = await db.scalar(
                select(VoiceSubscription)
                .where(VoiceSubscription.user_id == owner, VoiceSubscription.request_key == key)
                .with_for_update()
            )
            if prior:
                if (
                    prior.plan_id != self.settings.voice_test_plan_id
                    or prior.included_seconds != self.settings.voice_test_plan_seconds
                ):
                    raise HTTPException(409, "Request key belongs to different plan inputs.")
                if not prior.external_id:
                    raise HTTPException(
                        409,
                        "Checkout is pending reconciliation; retain the same request key.",
                    )
                return {
                    "subscription_id": prior.external_id,
                    "key_id": self.settings.razorpay_test_key_id,
                    "test_mode": True,
                }
            pending = await db.scalar(
                select(VoiceSubscription.id).where(
                    VoiceSubscription.user_id == owner,
                    VoiceSubscription.status.in_(("creating", "created", "active")),
                )
            )
            if pending:
                raise HTTPException(409, "An existing subscription requires reconciliation.")
            # Uncertainty survives restart. No retries of a timed-out subscription POST.
            local_id = "pending_" + uuid.uuid4().hex
            db.add(
                VoiceSubscription(
                    id=local_id,
                    user_id=owner,
                    request_key=key,
                    plan_id=self.settings.voice_test_plan_id,
                    included_seconds=self.settings.voice_test_plan_seconds,
                    status="creating",
                )
            )
            await db.commit()
        external = client or httpx.AsyncClient()
        try:
            response = await external.post(
                "https://api.razorpay.com/v1/subscriptions",
                auth=(
                    self.settings.razorpay_test_key_id,
                    self.settings.razorpay_test_key_secret.get_secret_value(),
                ),
                json={
                    "plan_id": self.settings.voice_test_plan_id,
                    "total_count": 1,
                    "quantity": 1,
                    "customer_notify": False,
                },
                timeout=15,
                follow_redirects=False,
            )
            if response.status_code not in (200, 201) or len(response.content) > 65536:
                raise ValueError()
            result = response.json()
            subscription_id = result["id"]
            if (
                not re.fullmatch(r"sub_[A-Za-z0-9]{1,100}", subscription_id)
                or result.get("plan_id") != self.settings.voice_test_plan_id
            ):
                raise ValueError()
            async with self.factory() as db:
                await self.lock_entitlement(db, owner)
                prior = await db.get(VoiceSubscription, local_id, with_for_update=True)
                assert prior is not None
                prior.external_id, prior.status = subscription_id, "created"
                await db.commit()
            return {
                "subscription_id": subscription_id,
                "key_id": self.settings.razorpay_test_key_id,
                "test_mode": True,
            }
        except Exception:
            raise HTTPException(
                503, "Checkout outcome is uncertain; operator reconciliation is required."
            ) from None
        finally:
            if client is None:
                await external.aclose()

    async def receive(self, raw: bytes, signature: str, event_id: str) -> dict[str, Any]:
        test_gate(self.settings)
        secret = self.settings.razorpay_test_webhook_secret.get_secret_value()
        if len(secret) < 32:
            raise HTTPException(503, "Test billing signature verification is unavailable.")
        if (
            not isinstance(signature, str)
            or not re.fullmatch(r"[a-fA-F0-9]{64}", signature)
            or not hmac.compare_digest(
                hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), signature.lower()
            )
        ):
            raise HTTPException(401, "Billing event signature is invalid.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", event_id or "") or not raw or len(raw) > 65536:
            raise HTTPException(422, "Billing event contract is invalid.")
        try:
            body = json.loads(raw, object_pairs_hook=_pairs)
            event = body["event"]
            entity = body["payload"]["subscription"]["entity"]
            sub_id = entity["id"]
            if (
                not isinstance(event, str)
                or len(event) > 80
                or not re.fullmatch(r"sub_[A-Za-z0-9]{1,100}", sub_id)
            ):
                raise ValueError()
            stamp = body["created_at"]
            if type(stamp) is not int:
                raise ValueError()
            when = datetime.fromtimestamp(stamp, UTC)
            if when.timestamp() > datetime.now(UTC).timestamp() + 30:
                raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
            raise HTTPException(422, "Billing event contract is invalid.") from None
        digest = hashlib.sha256(raw).hexdigest()
        async with self.factory() as db:
            hint = await db.scalar(
                select(VoiceSubscription).where(VoiceSubscription.external_id == sub_id)
            )
            if not hint:
                # Never manufacture customer ownership from webhook notes.
                raise HTTPException(409, "Subscription has no server-owned binding.")
            await self.lock_entitlement(db, hint.user_id)
            subscription = await db.get(VoiceSubscription, hint.id, with_for_update=True)
            assert subscription is not None
            prior = await db.get(VoiceBillingReceipt, event_id)
            if prior:
                if prior.digest != digest:
                    raise HTTPException(
                        409, "Billing event identifier conflicts with its stored payload."
                    )
                return {"received": True, "duplicate": True}
            if await db.scalar(
                select(VoiceBillingReceipt.id).where(VoiceBillingReceipt.digest == digest)
            ):
                return {"received": True, "duplicate": True}
            receipt = VoiceBillingReceipt(
                id=event_id, digest=digest, event=event, subscription_id=sub_id, status="ignored"
            )
            if subscription.last_event_at and when <= subscription.last_event_at:
                receipt.status = "stale"
            elif subscription.status in ("cancelled", "halted"):
                receipt.status = "terminal"
            elif entity.get("plan_id") != subscription.plan_id:
                receipt.status = "quarantined"
            elif event == "subscription.charged":
                try:
                    start, end = entity["current_start"], entity["current_end"]
                    if type(start) is not int or type(end) is not int or end <= start:
                        raise ValueError()
                    start, end = (
                        datetime.fromtimestamp(start, UTC),
                        datetime.fromtimestamp(end, UTC),
                    )
                    payment = body["payload"]["payment"]["entity"]
                    if (
                        not isinstance(payment, dict)
                        or payment.get("status") != "captured"
                        or payment.get("captured") is not True
                    ):
                        raise ValueError()
                    existing = await db.scalar(
                        select(VoiceFundingPeriod).where(
                            VoiceFundingPeriod.subscription_id == sub_id,
                            VoiceFundingPeriod.period_start == start,
                        )
                    )
                    if existing:
                        if (
                            existing.period_end != end
                            or existing.included_seconds != subscription.included_seconds
                        ):
                            raise ValueError()
                    else:
                        db.add(
                            VoiceFundingPeriod(
                                user_id=subscription.user_id,
                                subscription_id=sub_id,
                                plan_id=subscription.plan_id,
                                period_start=start,
                                period_end=end,
                                included_seconds=subscription.included_seconds,
                                status="funded_test",
                            )
                        )
                    subscription.status, subscription.last_event_at = "active", when
                    receipt.status = "processed_test"
                except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
                    receipt.status = "quarantined"
            elif event in ("subscription.cancelled", "subscription.halted"):
                subscription.status = event.split(".")[1]
                subscription.last_event_at = when
                receipt.status = "processed_test"
            # Insert the final receipt once. Queries above may autoflush; an early INSERT
            # followed by a status UPDATE would violate the append-only audit contract.
            db.add(receipt)
            await db.commit()
            return {"received": True, "duplicate": False}
