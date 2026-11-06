import unittest
from utils.intent_classifier import classify_intent


class TestIntentClassifier(unittest.TestCase):
    def test_buy_intent_price_and_specs(self):
        res = classify_intent("Re: Haas VF-2SS", "how much? I was just in Nashville. Too far to ship to California!")
        self.assertEqual(res["intent"], "buy")
        self.assertEqual(res["short_label"], "Comprador")

        res2 = classify_intent("Oportunidad Hyster", "Envíame fotos y precio por favor")
        self.assertEqual(res2["intent"], "buy")

        res3 = classify_intent("Re: CAT 320D", "where is the machine located?")
        self.assertEqual(res3["intent"], "buy")

        res4 = classify_intent("RE: Excavator", "Agradezco me pases info y valores por favor. Saludos")
        self.assertEqual(res4["intent"], "buy")

    def test_sell_intent(self):
        res = classify_intent("Equipos usados", "Tenemos para la venta 2 retroexcavadoras CAT 420F en Colombia.")
        self.assertEqual(res["intent"], "sell")
        self.assertEqual(res["short_label"], "Venta / Oferta")

        res2 = classify_intent("Used machinery", "Are you buying surplus equipment? We have machines for sale from our fleet.")
        self.assertEqual(res2["intent"], "sell")

    def test_optout_intent(self):
        res = classify_intent("RE: Question", "Julian, We don't have any cnc machinery and don't plan on buying any.")
        self.assertEqual(res["intent"], "optout")

        res2 = classify_intent("Re: Kevin", "Please note that I am no longer employed with the company.")
        self.assertEqual(res2["intent"], "optout")

        res3 = classify_intent("Re: Promo", "Por favor desuscribir mi correo de su base de datos. No me interesa.")
        self.assertEqual(res3["intent"], "optout")

    def test_general_intent(self):
        res = classify_intent("RE: Saludos", "Buen día, recibido. Muchas gracias.")
        self.assertEqual(res["intent"], "general")

        res2 = classify_intent("", "")
        self.assertEqual(res2["intent"], "general")


if __name__ == "__main__":
    unittest.main()

