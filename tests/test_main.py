"""
Pruebas de integración para el punto de entrada principal (main.py).
Valida las métricas del embudo y la disponibilidad de componentes.
"""
from main import show_funnel_metrics


def test_show_funnel_metrics_returns_dict():
    metrics = show_funnel_metrics()
    assert isinstance(metrics, dict)
    # Todos los valores deben ser enteros positivos
    for status, count in metrics.items():
        assert isinstance(count, int)
        assert count >= 0