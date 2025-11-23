"""
Модуль для создания слоя коренных берегов реки.
"""

from pathlib import Path

from qgis.core import QgsVectorLayer

from ..bedrock_banks import detect_bedrock_banks


def build_bedrock_banks_layer(
    rivers_layer: QgsVectorLayer,
    dem_layer: QgsVectorLayer,
    output_path: Path,
    buffer_distance: float = 200.0,
    height_threshold: float = 3.0,
    slope_threshold: float = 8.0,
) -> QgsVectorLayer:
    """
    Строит слой коренных берегов реки.

    Args:
        rivers_layer: Слой речной сети
        dem_layer: Слой DEM
        output_path: Путь для сохранения результата
        buffer_distance: Расстояние анализа от реки (м)
        height_threshold: Минимальный подъем относительно русла (м)
        slope_threshold: Минимальная крутизна склона (градусы)

    Returns:
        QgsVectorLayer: Слой с линиями коренных берегов
    """
    bedrock_banks = detect_bedrock_banks(
        rivers_layer,
        dem_layer,
        output_path,
        buffer_distance=buffer_distance,
        height_threshold=height_threshold,
        slope_threshold=slope_threshold,
    )

    return bedrock_banks
