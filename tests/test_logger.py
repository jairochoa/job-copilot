"""
Tests unitarios para el sistema de logging dual.
"""

from src.logger import LOG_FILE, setup_logger


def test_logger_creation_and_file_generation():
    """Verifica que el logger cree el archivo físico de log y maneje los niveles adecuados."""
    test_logger = setup_logger("test_runner")
    
    test_msg = "Mensaje de auditoría de prueba unitaria"
    test_logger.debug(test_msg)

    assert LOG_FILE.exists()
    
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        content = f.read()
        assert test_msg in content
