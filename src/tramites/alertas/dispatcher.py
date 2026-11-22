"""Despachador de alertas (CronJob). Recorre las suscripciones y 'envía' avisos.
En producción el envío usa el servicio gestionado de notificaciones (correo/SMS/mensajería);
aquí se registra en el log para poder demostrar el flujo sin proveedores externos."""
import json
from datetime import date

from ..common import datos
from .main import _con_estado, calendario


def ejecutar(hoy: date | None = None) -> list[dict]:
    hoy = hoy or date.today()
    enviados = []
    datos.set_origen("alertas-dispatcher")
    for s in datos.listar("suscripcion"):
        cfg = s["data"]
        digito = int(s["ruc"][-1])
        for it in _con_estado(calendario(digito, hoy.year), hoy):
            if 0 <= it["dias_restantes"] <= cfg["anticipacion_dias"]:
                for canal in cfg["canales"]:
                    aviso = {"ruc": s["ruc"][:2] + "*******" + s["ruc"][-2:], "canal": canal,
                             "obligacion": it["obligacion"], "vence": it["vence"], "dias": it["dias_restantes"]}
                    print(json.dumps({"evento": "alerta_enviada", **aviso}, ensure_ascii=False))
                    enviados.append(aviso)
    return enviados


if __name__ == "__main__":
    ejecutar()
