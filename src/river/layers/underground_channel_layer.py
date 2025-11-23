"""
Слой для отображения границ подземного русла реки.
"""

from pathlib import Path

from qgis.core import QgsProject, QgsVectorLayer


def build_underground_channel_layer(
    channel_layer: QgsVectorLayer,
    output_path: Path,
) -> QgsVectorLayer:
    """
    Создает и стилизует слой подземного русла.

    Args:
        channel_layer: Исходный слой с геометрией русла
        output_path: Путь для сохранения стилизованного слоя

    Returns:
        QgsVectorLayer: Стилизованный слой подземного русла
    """
    # Применяем стиль к слою
    _apply_style(channel_layer)

    # Переименовываем слой
    channel_layer.setName("Underground Channel")

    return channel_layer


def _apply_style(layer: QgsVectorLayer) -> None:
    """
    Применяет стиль к слою подземного русла.

    Стиль: голубой полупрозрачный полигон с темно-голубым контуром.

    Args:
        layer: Слой для стилизации
    """
    from qgis.core import QgsFillSymbol

    # Создаем символ заливки для полигонов
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "135,206,235,100",  # Голубой с прозрачностью (Light Sky Blue)
            "outline_color": "0,100,200,255",  # Темно-голубой контур
            "outline_width": "0.6",
            "outline_style": "solid",
        }
    )

    # Применяем символ к рендереру слоя
    layer.renderer().setSymbol(symbol)
    layer.triggerRepaint()
