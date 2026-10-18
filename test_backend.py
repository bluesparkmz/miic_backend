"""
Automated validation test for MIIC 2026 Backend (English Fields)
Tests:
- SQLite table creation & initial admin seed
- Public event registration submission (English & Portuguese aliases)
- Duplicate registration rejection
- Admin login and JWT token generation
- Protected admin registration listing
- Protected admin registration deletion
- Dashboard metrics calculation
"""
from fastapi.testclient import TestClient
from main import app
from database import engine, Base
from models import User, Registration

def run_tests():
    print(">>> 1. Initializing SQLite tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as client:
        print(">>> 2. Testing Root & Health Check...")
        res = client.get("/")
        assert res.status_code == 200, f"Root check failed: {res.text}"
        assert res.json()["status"] == "online"
        print("    [OK] Root endpoint online")

        print(">>> 3. Testing Public Registration Submission with English fields...")
        payload_en = {
            "full_name": "Carlos Silva",
            "email": "carlos.silva@investor.mz",
            "phone": "+258 84 123 4567",
            "organization": "Mozambique Capital Group",
            "country": "Mozambique",
            "participant_type": "0",
            "message": "Interest in energy and infrastructure sectors."
        }
        res = client.post("/api/registrations", json=payload_en)
        assert res.status_code == 201, f"Failed registration: {res.text}"
        data = res.json()
        assert data["id"] is not None
        assert data["full_name"] == "Carlos Silva"
        assert data["status"] == "pending"
        reg_id_1 = data["id"]
        print(f"    [OK] Registration 1 created with ID: {reg_id_1}")

        print(">>> 4. Testing Duplicate Email Prevention...")
        res_dup = client.post("/api/registrations", json=payload_en)
        assert res_dup.status_code == 400, f"Expected 400 for duplicate, got {res_dup.status_code}"
        print("    [OK] Duplicate email properly rejected with 400")

        print(">>> 5. Testing Registration with Portuguese frontend field aliases...")
        payload_pt = {
            "nome": "Sarah Johnson",
            "email": "sarah.j@globallogistics.com",
            "telefone": "+44 7911 123456",
            "organizacao": "UK Africa Trade",
            "pais": "United Kingdom",
            "tipo": "1",
            "mensagem": "Looking for joint ventures in port logistics."
        }
        res2 = client.post("/api/registrations", json=payload_pt)
        assert res2.status_code == 201, f"Failed PT alias registration: {res2.text}"
        assert res2.json()["full_name"] == "Sarah Johnson"
        reg_id_2 = res2.json()["id"]
        print(f"    [OK] Registration 2 created via form aliases with ID: {reg_id_2}")

        print(">>> 6. Testing Unauthorized Access to Protected Routes...")
        res_unauth = client.get("/api/registrations")
        assert res_unauth.status_code == 401, f"Expected 401 Unauthorized, got {res_unauth.status_code}"
        print("    [OK] Unauthorized access blocked (401)")

        print(">>> 7. Testing Admin Login (admin / admin2026)...")
        login_res = client.post("/api/auth/login", json={"username": "admin", "password": "admin2026"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        assert token is not None
        headers = {"Authorization": f"Bearer {token}"}
        print("    [OK] Admin authenticated, JWT token acquired")

        print(">>> 8. Testing Admin /api/auth/me...")
        me_res = client.get("/api/auth/me", headers=headers)
        assert me_res.status_code == 200
        assert me_res.json()["username"] == "admin"
        assert me_res.json()["is_admin"] is True
        print("    [OK] /api/auth/me verified")

        print(">>> 9. Testing Listing Registrations...")
        list_res = client.get("/api/registrations", headers=headers)
        assert list_res.status_code == 200
        registrations = list_res.json()
        assert len(registrations) == 2
        print(f"    [OK] Listed {len(registrations)} registrations")

        print(">>> 10. Testing Search Filter...")
        search_res = client.get("/api/registrations?search=Carlos", headers=headers)
        assert len(search_res.json()) == 1
        assert search_res.json()[0]["full_name"] == "Carlos Silva"
        print("    [OK] Search filter by name confirmed")

        print(">>> 11. Testing Status Update...")
        status_res = client.patch(
            f"/api/registrations/{reg_id_1}/status",
            json={"status": "confirmed"},
            headers=headers
        )
        assert status_res.status_code == 200
        assert status_res.json()["status"] == "confirmed"
        print("    [OK] Status updated to 'confirmed'")

        print(">>> 12. Testing Dashboard Stats (English)...")
        stats_res = client.get("/api/admin/stats", headers=headers)
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["total_registrations"] == 2
        assert stats["confirmed"] == 1
        assert stats["pending"] == 1
        print(f"    [OK] Dashboard stats: {stats}")

        print(">>> 13. Testing Registration Deletion (user requirement)...")
        del_res = client.delete(f"/api/registrations/{reg_id_2}", headers=headers)
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True
        print(f"    [OK] Registration {reg_id_2} deleted successfully")

        # Verify deletion in database
        list_after = client.get("/api/registrations", headers=headers).json()
        assert len(list_after) == 1
        assert list_after[0]["id"] == reg_id_1
        print("    [OK] Verified item was removed from database")

        print("\n" + "=" * 50)
        print("ALL 13 TESTS PASSED SUCCESSFULLY! :)")
        print("=" * 50)

if __name__ == "__main__":
    run_tests()
