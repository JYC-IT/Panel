import unittest
from app import create_app
import db
from connectors import close_crm


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test-secret"
        self.client = self.app.test_client()

    def test_unauthenticated_redirect(self):
        """Usuarios no autenticados deben ser redirigidos al login."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

    def test_authenticated_dashboard(self):
        """Dashboard principal accesible para usuarios logueados."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_email"] = "admin@jycexports.com"
            sess["user_role"] = "admin"
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"JYC Equipment", res.data)

    def test_weekly_report(self):
        """Reporte semanal accesible."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_email"] = "admin@jycexports.com"
            sess["user_role"] = "admin"
        res = self.client.get("/weekly-report")
        self.assertEqual(res.status_code, 200)

    def test_performance_view(self):
        """Vista de Performance y exportación CSV."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_email"] = "admin@jycexports.com"
            sess["user_role"] = "admin"
        res = self.client.get("/performance")
        self.assertEqual(res.status_code, 200)

        # Prueba de exportación CSV
        res_csv = self.client.get("/performance/export.csv?start_date=2026-10-01&end_date=2026-10-20")
        self.assertIn(res_csv.status_code, (200, 302))
        if res_csv.status_code == 200:
            self.assertEqual(res_csv.mimetype, "text/csv")
            self.assertIn(b"Asesor Comercial", res_csv.data)

    def test_campaign_detail(self):
        """Vista de detalle de campaña existente."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_email"] = "admin@jycexports.com"
            sess["user_role"] = "admin"
        res = self.client.get("/campaign/1")
        self.assertIn(res.status_code, (200, 404))

    def test_roy_jones_excluded(self):
        """Roy Jones debe estar estrictamente excluido del sistema."""
        self.assertIn("rjones@jycexports.com", close_crm.EXCLUDED_EMAILS)
        self.assertIn("royjones@jycexports.com", close_crm.EXCLUDED_EMAILS)
        self.assertIn("user_fFN8XRtibi7NPtCPiZSM6Z5cHmw87PYKDJ8Xg6tYv4D", close_crm.EXCLUDED_USER_IDS)
        self.assertIn("user_8utZW4zSBIE0JHZ3Ef4zSNalKgZVRb9Dxz46M3Dtxrv", close_crm.EXCLUDED_USER_IDS)
        self.assertNotIn("rjones@jycexports.com", close_crm.DEFAULT_AGENT_EMAILS)
        self.assertNotIn("royjones@jycexports.com", close_crm.DEFAULT_AGENT_EMAILS)

        # Chequear que la consulta de KPIs en BD no devuelva a Roy
        kpis = db.get_agent_kpis()
        for k in kpis:
            self.assertNotIn("roy", (k.get("name") or "").lower())

    def test_carlos_cordoba_excluded(self):
        """Carlos Córdoba debe estar estrictamente excluido del sistema comercial y reportes."""
        self.assertIn("ccordoba@jycexports.com", close_crm.EXCLUDED_EMAILS)
        self.assertIn("user_Aa5pIAD0HQvnxk1hAMdvdBz3UAjW1NaVrKFMfJpmpaK", close_crm.EXCLUDED_USER_IDS)
        self.assertNotIn("ccordoba@jycexports.com", close_crm.DEFAULT_AGENT_EMAILS)

        # Chequear que la consulta de KPIs en BD no devuelva a Carlos
        kpis = db.get_agent_kpis()
        for k in kpis:
            self.assertNotIn("carlos", (k.get("name") or "").lower())

    def test_timezone_conversion(self):
        """Las horas UTC de Close CRM deben convertirse a UTC-5 (ej. 21:15 UTC -> 04:15 PM)."""
        from services.audit_engine import to_local_datetime
        dt = to_local_datetime("2026-10-28T21:15:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 16)
        self.assertEqual(dt.minute, 15)
        self.assertEqual(dt.strftime("%I:%M %p"), "04:15 PM")

    def test_manual_campaign_creation(self):
        """Creación manual de campaña para contingencia."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_email"] = "admin@jycexports.com"
            sess["user_role"] = "admin"

        res = self.client.post("/campaign/create", data={
            "name": "TEST CAMPAIGN MANUAL CONTINGENCIA",
            "source": "constantcontact",
            "start_date": "2026-10-27",
            "sent_count": 48000,
            "opens_count": 15000,
            "clicks_count": 300,
            "reply_to_email": "test@jycexports.com"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"TEST CAMPAIGN MANUAL", res.data)

    def test_campaign_intent_classification_and_filter(self):
        """Verifica que el detalle de campaña filtre por intención y exporte CSV con columna Intención."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_email"] = "admin@jycexports.com"
            sess["user_role"] = "admin"

        # Detalle de campaña con filtro por compradores
        res = self.client.get("/campaign/1?intent=buy")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Calificaci\xc3\xb3n", res.data)
        self.assertIn(b"Compradores", res.data)

        # Exportación CSV con Intención
        res_csv = self.client.get("/campaign/1/export.csv")
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("Intención".encode("utf-8"), res_csv.data)

    def test_update_reply_intent(self):
        """Permite a un asesor o admin cambiar manualmente la intención de una respuesta."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_email"] = "admin@jycexports.com"
            sess["user_role"] = "admin"

        with db.get_conn() as conn:
            row = conn.execute("SELECT id FROM replies LIMIT 1").fetchone()
        if row:
            rid = row["id"]
            res = self.client.post(f"/reply/{rid}/intent", data={"intent": "buy"}, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            with db.get_conn() as conn:
                updated = conn.execute("SELECT intent FROM replies WHERE id = ?", (rid,)).fetchone()
                self.assertEqual(updated["intent"], "buy")


if __name__ == "__main__":
    unittest.main()
