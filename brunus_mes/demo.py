"""Eventos de demonstração pedidos pelo master, sem acesso a equipamentos reais."""

import os

from .services import _authorize


def generate_demo_event(event, main_line, profile, path=None, now=None):
    """Reutiliza as regras do simulador numa sessão explicitamente de demonstração."""
    _authorize(profile, {"master"})
    if os.environ.get("BRUNUS_DEMO_MODE") != "1":
        raise PermissionError("A geração manual de eventos só está disponível no modo de demonstração.")
    if event not in {"OK", "REJEITADA", "ERRO"}:
        raise ValueError("Escolha um evento de produção ou avaria válido.")
    from simulador_continuo import ciclo_fabrica_avancado

    return ciclo_fabrica_avancado(path, event=event, main_line=main_line, now=now)
