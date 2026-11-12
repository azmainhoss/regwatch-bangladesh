import uuid
from datetime import date
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.app.modules.sources.connector.bangladesh_bank import BangladeshBankConnector
from backend.app.modules.sources.connector.base import AntiBotChallenge, DiscoveryResult


# Sample HTML fixture mimicking official Bangladesh Bank circulars listing
MOCK_BB_CIRCULAR_HTML = """
<!DOCTYPE html>
<html>
<head><title>Bangladesh Bank Circulars</title></head>
<body>
  <div class="content">
    <table class="table">
      <tr><th>Date</th><th>Title</th><th>English</th><th>Bangla</th></tr>
      <tr>
        <td>27-11-2024</td>
        <td class="text-left"> BRPD Circular No. 15 : Master Policy on Loan Classification and Provisioning Alignment with IFRS 9 </td>
        <td><a href="/mediaroom/circulars/brpd/nov272024brpd15e.pdf" target="_blank">Download</a></td>
        <td>Not Available</td>
      </tr>
      <tr>
        <td>01-12-2024</td>
        <td class="text-left"> BRPD Circular No. 16 : Guidelines on Ultimate Beneficial Ownership (UBO) Disclosure </td>
        <td><a href="/mediaroom/circulars/brpd/dec012024brpd16e.pdf" target="_blank">Download</a></td>
        <td>Not Available</td>
      </tr>
    </table>
  </div>
</body>
</html>
"""

MOCK_IMPERVA_CHALLENGE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Challenge</title>
<script type="text/javascript">window["bobcmn"] = "101110101010112";</script>
</head>
<body>
  <b>What code is in the image?</b>
  <input type="text" name="answer"/>
  Your support ID is: 2165770898338673683 .
</body>
</html>
"""


_REAL_POST = httpx.AsyncClient.post
_REAL_GET = httpx.AsyncClient.get


def _site_only(real, reply):
    """Answers requests to bb.org.bd with `reply`; the test's own API calls go through."""
    async def fake(self, url, *args, **kwargs):
        if "bb.org.bd" in str(url):
            return reply
        return await real(self, url, *args, **kwargs)
    return fake


def test_bangladesh_bank_connector_html_parsing():
    connector = BangladeshBankConnector()
    candidates = connector.parse_listing_html(
        MOCK_BB_CIRCULAR_HTML,
        "https://www.bb.org.bd/en/index.php/mediaroom/circular"
    )

    assert len(candidates) == 2

    c1 = candidates[0]
    assert c1.reference_number == "BRPD Circular No. 15"
    assert c1.department_code == "BRPD"
    assert c1.publication_date == date(2024, 11, 27)
    assert c1.file_url == "https://www.bb.org.bd/mediaroom/circulars/brpd/nov272024brpd15e.pdf"

    c2 = candidates[1]
    assert c2.reference_number == "BRPD Circular No. 16"
    assert c2.department_code == "BRPD"
    assert c2.publication_date == date(2024, 12, 1)
    assert c2.file_url == "https://www.bb.org.bd/mediaroom/circulars/brpd/dec012024brpd16e.pdf"


def test_anti_bot_challenge_detection():
    connector = BangladeshBankConnector()
    challenge = connector.detect_anti_bot_challenge(MOCK_IMPERVA_CHALLENGE_HTML, 200)

    assert challenge is not None
    assert challenge.is_blocked is True
    assert challenge.challenge_type == "IMPERVA_TSPD_CAPTCHA"
    assert challenge.support_id == "2165770898338673683"
    assert "retried" in challenge.details


@pytest.mark.asyncio
async def test_source_monitoring_run_with_mocked_network():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register admin user for authentication
        uid = uuid.uuid4().hex[:6]
        user_resp = await client.post("/api/v1/auth/register", json={
            "email": f"source_admin_{uid}@regwatch.bd",
            "password": "Password12345!",
            "full_name": "Source Admin"
        })
        plain_headers = {"Authorization": f"Bearer {user_resp.json()['access_token']}"}

        # Source administration is reserved for platform superusers
        from backend.app.tests.factories import make_user
        _admin, token = await make_user(is_superuser=True)
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Get existing Bangladesh Bank source from database
        sources_resp = await client.get("/api/v1/sources")
        assert sources_resp.status_code == 200
        sources = sources_resp.json()
        assert len(sources) >= 1
        bb_source = sources[0]
        source_id = bb_source["id"]

        # A freshly registered (non-admin) user cannot trigger a crawl
        denied = await client.post(f"/api/v1/sources/{source_id}/trigger", headers=plain_headers)
        assert denied.status_code == 403

        # 3. Simulate a successful new-circular check (date-filter POST) using mocked HTML.
        # Downloads that follow get a 404 so nothing leaves the machine.
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = MOCK_BB_CIRCULAR_HTML
        not_found = AsyncMock()
        not_found.status_code = 404
        not_found.text = "Not Found"
        not_found.content = b"Not Found"
        with patch.object(httpx.AsyncClient, "post", new=_site_only(_REAL_POST, mock_resp)), \
                patch.object(httpx.AsyncClient, "get", new=_site_only(_REAL_GET, not_found)):

            run_resp = await client.post(f"/api/v1/sources/{source_id}/trigger", headers=headers)
            assert run_resp.status_code == 200
            run_data = run_resp.json()
            assert run_data["status"] == "COMPLETED"
            assert run_data["outcome"] == "OK"
            assert run_data["candidate_links_discovered"] == 2
            assert run_data["access_restricted"] is False

        # 4. Check Discovery Review Queue
        disc_resp = await client.get("/api/v1/sources/discoveries", headers=headers)
        assert disc_resp.status_code == 200
        discoveries = disc_resp.json()
        assert len(discoveries) >= 2

        # 5. Reject one discovery with a human reason
        d_to_reject = discoveries[0]
        reject_resp = await client.post(
            f"/api/v1/sources/discoveries/{d_to_reject['id']}/reject",
            headers=headers,
            json={"reason": "Internal draft not for public distribution."}
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "REJECTED"
        assert reject_resp.json()["rejection_reason"] == "Internal draft not for public distribution."

        # 6. Simulate a bot check page: the run fails and is retried later, never "0 new"
        mock_challenge_resp = AsyncMock()
        mock_challenge_resp.status_code = 200
        mock_challenge_resp.text = MOCK_IMPERVA_CHALLENGE_HTML
        with patch.object(httpx.AsyncClient, "post", new=_site_only(_REAL_POST, mock_challenge_resp)):

            blocked_run_resp = await client.post(f"/api/v1/sources/{source_id}/trigger", headers=headers)
            assert blocked_run_resp.status_code == 200
            blocked_data = blocked_run_resp.json()
            assert blocked_data["status"] == "FAILED_RETRY"
            assert blocked_data["outcome"] == "CHALLENGE"
            assert blocked_data["access_restricted"] is True
            assert blocked_data["access_restriction_details"]["challenge_type"] == "IMPERVA_TSPD_CAPTCHA"

        # 7. Verify source record updated with restriction status
        source_detail = await client.get(f"/api/v1/sources/{source_id}")
        assert source_detail.status_code == 200
        assert source_detail.json()["access_restriction_status"] == "IMPERVA_TSPD_CAPTCHA"

        # 8. Admin toggles source active status
        toggle_resp = await client.patch(
            f"/api/v1/sources/{source_id}",
            headers=headers,
            json={"is_active": False, "polling_frequency_minutes": 120}
        )
        assert toggle_resp.status_code == 200
        assert toggle_resp.json()["is_active"] is False
        assert toggle_resp.json()["polling_frequency_minutes"] == 120

