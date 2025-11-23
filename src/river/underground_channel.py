"""
Модуль для выделения границ подземного русла реки.
Использует анализ DEM для определения зоны с пониженным рельефом вдоль реки.
"""

from pathlib import Path

import processing
from qgis.core import (
    QgsRasterLayer,
    QgsVectorLayer,
)


def detect_underground_channel(
    rivers_layer: QgsVectorLayer,
    dem_layer: QgsRasterLayer,
    output_path: Path,
    buffer_distance: float = 50.0,
) -> QgsVectorLayer:
    """
    Определяет границы подземного русла реки.

    Алгоритм:
    1. Создает буферную зону вокруг линий рек
    2. Извлекает статистику высот внутри буфера для определения зоны пониженного рельефа
    3. Определяет границы русла на основе анализа высот

    Args:
        rivers_layer: Векторный слой речной сети (линии)
        dem_layer: Слой цифровой модели рельефа (DEM)
        output_path: Путь для сохранения результата
        buffer_distance: Расстояние буфера от оси реки (м)

    Returns:
        QgsVectorLayer: Слой с полигонами подземного русла
    """
    # Шаг 1: Создаем буферную зону вокруг речной сети
    buffer_result = processing.run(
        "native:buffer",
        {
            "INPUT": rivers_layer,
            "DISTANCE": buffer_distance,
            "SEGMENTS": 20,
            "END_CAP_STYLE": 0,  # Round
            "JOIN_STYLE": 0,  # Round
            "MITER_LIMIT": 2,
            "DISSOLVE": True,  # Объединить все буферы в один полигон
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    buffer_layer = buffer_result["OUTPUT"]

    # Шаг 2: Создаем сетку точек внутри буфера для анализа высот
    # Получаем границы буфера
    extent = buffer_layer.extent()
    spacing = 10  # Расстояние между точками сетки (м)

    grid_result = processing.run(
        "native:pixelstopoints",
        {
            "INPUT_RASTER": dem_layer,
            "RASTER_BAND": 1,
            "FIELD_NAME": "elevation",
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    grid_points = grid_result["OUTPUT"]

    # Шаг 3: Оставляем только точки внутри буфера
    clipped_points = processing.run(
        "native:clip",
        {
            "INPUT": grid_points,
            "OVERLAY": buffer_layer,
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    points_in_buffer = clipped_points["OUTPUT"]

    # Шаг 4: Создаем зону русла на основе низких высот
    # Извлекаем статистику высот
    stats_result = processing.run(
        "qgis:basicstatisticsforfields",
        {
            "INPUT_LAYER": points_in_buffer,
            "FIELD_NAME": "elevation",
        },
    )

    # Используем перцентиль для определения порога низких высот
    # Берем нижние 30% высот как зону русла
    percentile_30 = stats_result["MIN"] + (stats_result["MAX"] - stats_result["MIN"]) * 0.3

    # Фильтруем точки с низкими высотами
    low_elevation_points = processing.run(
        "native:extractbyexpression",
        {
            "INPUT": points_in_buffer,
            "EXPRESSION": f'"elevation" <= {percentile_30}',
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    low_points = low_elevation_points["OUTPUT"]

    # Шаг 5: Создаем полигон русла через concave hull (вогнутую оболочку)
    channel_boundary = processing.run(
        "qgis:concavehull",
        {
            "INPUT": low_points,
            "ALPHA": 0.5,  # Параметр детализации границы (0-1)
            "HOLES": True,
            "NO_MULTIGEOMETRY": False,
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    channel_hull = channel_boundary["OUTPUT"]

    # Шаг 6: Сглаживаем границы для более естественного вида
    smoothed_result = processing.run(
        "native:smoothgeometry",
        {
            "INPUT": channel_hull,
            "ITERATIONS": 5,
            "OFFSET": 0.25,
            "MAX_ANGLE": 180,
            "OUTPUT": str(output_path),
        },
    )

    # Шаг 7: Загружаем результат как слой
    underground_channel_layer = QgsVectorLayer(
        str(output_path), "underground_channel_raw", "ogr"
    )

    return underground_channel_layer
