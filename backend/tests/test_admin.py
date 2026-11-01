"""Real permission, audit and candidate dossier contracts on disposable storage."""

import asyncio
import os
import unittest
import uuid
from datetime import date

import httpx
from pydantic import ValidationError

from app.schemas import Register, ProfileUpdate


class DossierValidation(unittest.TestCase):
    def test_normalizes_optional_candidate_details_and_rejects_privilege_escalation(
        self,
    ):
        data = ProfileUpdate(
            name="Candidate",
            skills=["suporte"],
            birth_date="14/05/1990",
            cpf="529.982.247-25",
            phone="(61) 99999-1234",
            candidate_state="Distrito Federal",
            linkedin_url="https://www.linkedin.com/in/example",
            desired_salary=5000,
        )
        self.assertEqual(data.birth_date, date(1990, 5, 14))
        self.assertEqual(data.cpf, "52998224725")
        self.assertEqual(data.phone, "+5561999991234")
        self.assertEqual(data.candidate_state, "DF")
        for role in ["super_admin", "moderator"]:
            with self.assertRaises(ValidationError):
                Register(
                    email="candidate@example.com",
                    password="Disposable-password12",
                    name="Test",
                    role=role,
                    consent=True,
                    privacy_version="2026-01",
                )
        for details in [
            {"cpf": "00000000000"},
            {"birth_date": "31/02/1990"},
            {"linkedin_url": "https://linkedin.com.attacker.example/profile"},
        ]:
            with self.assertRaises(ValidationError):
                ProfileUpdate(name="Candidate", skills=["suporte"], **details)


@unittest.skipUnless(
    os.getenv("VAGOU_TEST_URL"), "Disposable integration stack required"
)
class AdminContract(unittest.TestCase):
    def test_staff_boundaries_kyb_audit_owner_and_pdf_gate(self):
        async def scenario():
            from sqlalchemy import select, delete
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
            from app.models import User, Job, AdminAudit, SystemNotification
            from app.config import settings
            from app.security import token, cipher
            from app.passwords import hash_password

            engine = create_async_engine(settings().database_url)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            ids = [uuid.uuid4() for _ in range(4)]
            headers = {}
            try:
                async with sessions.begin() as db:
                    for identifier, role in zip(
                        ids, ["super_admin", "moderator", "candidate", "recruiter"]
                    ):
                        user = User(
                            id=identifier,
                            email=f"{identifier}@example.com",
                            name="CI " + role,
                            role=role,
                            email_verified=True,
                            is_premium=False,
                            privacy_version="2026-01",
                            password_hash=hash_password("Disposable-Admin-Password!"),
                            company_cnpj=(
                                "04252011000110" if role == "recruiter" else None
                            ),
                            company_name="Empresa CI" if role == "recruiter" else None,
                            company_contact_email=(
                                f"{identifier}@example.com"
                                if role == "recruiter"
                                else None
                            ),
                        )
                        db.add(user)
                        await db.flush()
                        headers[role] = {"Authorization": "Bearer " + token(user)}
                payload = {
                    "title": "Analista de Suporte",
                    "company": "Empresa CI",
                    "description": "Atendimento técnico de chamados e redes corporativas.",
                    "salary_min": 3000,
                    "salary_max": 5000,
                    "modality": "onsite",
                    "location": "Brasília / DF",
                    "keywords": ["suporte", "redes"],
                }
                async with httpx.AsyncClient(
                    base_url=os.environ["VAGOU_TEST_URL"], timeout=15
                ) as client:

                    async def call(method, path, role, body=None, status=200):
                        result = await client.request(
                            method, "/v1" + path, headers=headers[role], json=body
                        )
                        self.assertEqual(result.status_code, status, result.text)
                        return result.json() if result.content else None

                    await call("GET", "/admin/dashboard", "candidate", status=403)
                    await call("GET", "/admin/users", "moderator", status=403)
                    await call(
                        "PATCH",
                        f"/admin/users/{ids[2]}",
                        "moderator",
                        {"is_premium": True},
                        403,
                    )
                    await call("GET", "/radar", "candidate", status=403)
                    await call(
                        "PATCH",
                        f"/admin/users/{ids[2]}",
                        "super_admin",
                        {"is_premium": True},
                    )
                    await call("GET", "/radar", "candidate")
                    job = await call("POST", "/jobs", "recruiter", payload, 201)
                    self.assertEqual(job["moderation_status"], "pending")
                    await call(
                        "POST",
                        f"/admin/jobs/{job['id']}/actions",
                        "moderator",
                        {"action": "reject"},
                        422,
                    )
                    await call(
                        "POST",
                        f"/admin/jobs/{job['id']}/actions",
                        "moderator",
                        {"action": "reject", "note": "Corrija a descrição da vaga."},
                    )
                    await call(
                        "PATCH",
                        f"/admin/users/{ids[3]}",
                        "moderator",
                        {"company_verified": True},
                    )
                    auto = await call("POST", "/jobs", "recruiter", payload, 201)
                    self.assertEqual(auto["moderation_status"], "approved")
                    self.assertEqual(auto["moderated_by_user_id"], str(ids[3]))
                    feed = await call("GET", "/internal-jobs", "candidate")
                    match = next(
                        item
                        for item in feed["items"]
                        if item["job"]["id"] == auto["id"]
                    )
                    self.assertTrue(match["job"]["company_verified"])
                    await call(
                        "POST",
                        f"/jobs/{auto['id']}/applications",
                        "candidate",
                        status=409,
                    )
                    saved = await call(
                        "PUT",
                        "/me/profile",
                        "candidate",
                        {
                            "name": "Candidate",
                            "skills": ["suporte"],
                            "birth_date": "14/05/1990",
                            "cpf": "529.982.247-25",
                            "candidate_city": "Brasília",
                            "candidate_state": "DF",
                            "phone": "(61) 99999-1234",
                        },
                    )
                    self.assertEqual(saved["cpf"], "52998224725")
                    self.assertEqual(saved["birth_date"], "1990-05-14")
                    async with sessions() as db:
                        candidate = await db.get(User, ids[2])
                        self.assertNotIn("52998224725", candidate.cpf_encrypted)
                        self.assertEqual(
                            cipher().decrypt(candidate.cpf_encrypted.encode()).decode(),
                            "52998224725",
                        )
                        audits = (
                            await db.scalars(
                                select(AdminAudit).where(
                                    AdminAudit.target_id.in_(
                                        [
                                            ids[2],
                                            ids[3],
                                            uuid.UUID(job["id"]),
                                            uuid.UUID(auto["id"]),
                                        ]
                                    )
                                )
                            )
                        ).all()
                        self.assertTrue(
                            any(
                                a.action == "job_reject"
                                and a.actor_id == ids[1]
                                and a.details["note"]
                                for a in audits
                            )
                        )
                        notice = await db.scalar(
                            select(SystemNotification).where(
                                SystemNotification.user_id == ids[3]
                            )
                        )
                        self.assertNotIn("Corrija", notice.payload_encrypted)
                        self.assertIn(
                            "Corrija",
                            cipher()
                            .decrypt(notice.payload_encrypted.encode())
                            .decode(),
                        )
                    await call(
                        "PATCH",
                        f"/admin/users/{ids[2]}",
                        "super_admin",
                        {"is_premium": False},
                    )
                    await call("GET", "/radar", "candidate", status=403)
                    await call(
                        "PATCH",
                        f"/admin/users/{ids[3]}",
                        "super_admin",
                        {"is_active": False},
                    )
                    await call("GET", "/me", "recruiter", status=401)
                    async with sessions() as db:
                        archived = await db.get(Job, uuid.UUID(auto["id"]))
                        self.assertFalse(archived.active)
            finally:
                async with sessions.begin() as db:
                    await db.execute(delete(User).where(User.id.in_(ids)))
                    await db.execute(
                        delete(AdminAudit).where(AdminAudit.actor_id.is_(None))
                    )
                await engine.dispose()

        asyncio.run(scenario())

    def test_owner_promotion_requires_verified_authentication_and_cannot_be_revoked(
        self,
    ):
        async def scenario():
            from sqlalchemy import select, delete
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
            from app.config import settings
            from app.models import User, AdminAudit
            from app.security import token
            from app.passwords import hash_password

            engine = create_async_engine(settings().database_url)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            identifier = uuid.uuid4()
            try:
                async with sessions.begin() as db:
                    self.assertIsNone(
                        await db.scalar(
                            select(User).where(User.email == "rbrilhante001@gmail.com")
                        )
                    )
                    user = User(
                        id=identifier,
                        email="rbrilhante001@gmail.com",
                        name="Proprietário CI",
                        role="candidate",
                        is_premium=False,
                        email_verified=False,
                        privacy_version="2026-01",
                        password_hash=hash_password("Disposable-Owner-Password!"),
                    )
                    db.add(user)
                    await db.flush()
                    headers = {"Authorization": "Bearer " + token(user)}
                async with httpx.AsyncClient(
                    base_url=os.environ["VAGOU_TEST_URL"]
                ) as client:
                    self.assertEqual(
                        (await client.get("/v1/me", headers=headers)).status_code, 401
                    )
                    async with sessions.begin() as db:
                        user = await db.get(User, identifier)
                        user.email_verified = True
                    response = await client.get("/v1/me", headers=headers)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["role"], "super_admin")
                    self.assertTrue(response.json()["is_admin"])
                    self.assertTrue(response.json()["is_premium"])
                    denied = await client.patch(
                        "/v1/admin/users/" + str(identifier),
                        headers=headers,
                        json={"is_premium": False, "role": "candidate"},
                    )
                    self.assertEqual(denied.status_code, 409, denied.text)
            finally:
                async with sessions.begin() as db:
                    await db.execute(delete(User).where(User.id == identifier))
                await engine.dispose()

        asyncio.run(scenario())
