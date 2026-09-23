"""
Pruebas unitarias para el orquestador principal (HU-06).
Valida argumentos CLI y consulta de métricas del embudo.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Asegurar que la raíz del proyecto esté en sys.path para importar main.py
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import main, show_funnel_metrics


@patch("main.get_db_connection")
def test_show_funnel_metrics_runs_cleanly(mock_get_conn):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        ("SCRAPED", 2),
        ("FILTERED_OUT", 4),
        ("SCORED", 4),
        ("GENERATED", 4),
        ("APPLIED", 1),
    ]
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value.__enter__.return_value = mock_conn

    show_funnel_metrics()
    assert mock_cursor.execute.called


@patch("main.show_funnel_metrics")
def test_cli_stats_flag(mock_show_metrics):
    with patch.object(sys, "argv", ["main.py", "--stats"]):
        main()
        mock_show_metrics.assert_called_once()
