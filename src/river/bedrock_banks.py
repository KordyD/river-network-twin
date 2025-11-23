"""
Модуль для выделения коренных берегов реки.
Использует анализ DEM для определения участков с резким повышением рельефа вдоль реки.
"""

import math
from pathlib import Path

import processing
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant


def detect_bedrock_banks(
    rivers_layer: QgsVectorLayer,
    dem_layer: QgsRasterLayer,
    output_path: Path,
    buffer_distance: float = 200.0,
    height_threshold: float = 3.0,
    slope_threshold: float = 8.0,
    transect_spacing: float = 75.0,
    point_spacing: float = 15.0,
    min_consecutive: int = 3,
) -> QgsVectorLayer:
    """
    Определяет линии коренных берегов реки.

    Алгоритм:
    1. Создает поперечные профили вдоль реки
    2. На каждом профиле анализирует изменение высоты от русла наружу
    3. Находит точки с резким подъемом (коренные берега)
    4. Соединяет точки в линию и сглаживает

    Args:
        rivers_layer: Векторный слой речной сети (линии)
        dem_layer: Слой цифровой модели рельефа (DEM)
        output_path: Путь для сохранения результата
        buffer_distance: Расстояние анализа от реки (м)
        height_threshold: Минимальный подъем относительно русла (м)
        slope_threshold: Минимальная крутизна склона (градусы)
        transect_spacing: Расстояние между поперечными профилями (м)
        point_spacing: Расстояние между точками на профиле (м)
        min_consecutive: Количество последовательных точек для подтверждения

    Returns:
        QgsVectorLayer: Слой с линиями коренных берегов
    """
    print(f"Начало выделения коренных берегов с параметрами:", flush=True)
    print(f"  buffer_distance={buffer_distance}м", flush=True)
    print(f"  height_threshold={height_threshold}м", flush=True)
    print(f"  slope_threshold={slope_threshold}°", flush=True)

    # Шаг 1: Создаем поперечные профили вдоль реки
    print("Создание поперечных профилей...", flush=True)
    transects = processing.run(
        "native:transect",
        {
            "INPUT": rivers_layer,
            "LENGTH": buffer_distance,
            "ANGLE": 90.0,
            "SIDE": 2,  # обе стороны
            "DISTANCE": transect_spacing,  # интервал между профилями
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    transects_layer = transects["OUTPUT"]

    # Шаг 2: Создаем точки вдоль каждого поперечного профиля
    print("Создание точек вдоль профилей...", flush=True)
    points_on_transects = processing.run(
        "native:pointsalonglines",
        {
            "INPUT": transects_layer,
            "DISTANCE": point_spacing,
            "START_OFFSET": 0,
            "END_OFFSET": 0,
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    points_layer = points_on_transects["OUTPUT"]

    # Шаг 3: Добавляем высоты из DEM к каждой точке
    print("Извлечение высот из DEM...", flush=True)
    points_with_elevation = processing.run(
        "native:rastersampling",
        {
            "INPUT": points_layer,
            "RASTERCOPY": dem_layer,
            "COLUMN_PREFIX": "elev_",
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    points_with_z = points_with_elevation["OUTPUT"]

    # Шаг 4: Анализируем каждый профиль и находим точки коренных берегов
    print("Анализ профилей и поиск коренных берегов...", flush=True)
    bedrock_points = _analyze_transects_for_bedrock(
        points_with_z,
        rivers_layer,
        height_threshold,
        slope_threshold,
        min_consecutive,
        point_spacing,
    )

    if not bedrock_points:
        print("Коренные берега не обнаружены", flush=True)
        # Создаем пустой слой
        empty_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3857", "bedrock_banks", "memory"
        )
        return empty_layer

    print(f"Найдено {len(bedrock_points)} точек коренных берегов", flush=True)

    # Шаг 5: Создаем слой с точками
    bedrock_points_layer = _create_points_layer(bedrock_points)

    # Шаг 6: Соединяем точки в линию
    print("Соединение точек в линию...", flush=True)
    bedrock_line = processing.run(
        "native:pointstopath",
        {
            "INPUT": bedrock_points_layer,
            "ORDER_FIELD": "distance_along",
            "GROUP_FIELD": "side",  # группируем по сторонам реки
            "OUTPUT": "TEMPORARY_OUTPUT",
        },
    )

    bedrock_line_layer = bedrock_line["OUTPUT"]

    # Шаг 7: Сглаживаем линию для естественного вида
    print("Сглаживание линии...", flush=True)
    smoothed_result = processing.run(
        "native:smoothgeometry",
        {
            "INPUT": bedrock_line_layer,
            "ITERATIONS": 5,
            "OFFSET": 0.25,
            "MAX_ANGLE": 180,
            "OUTPUT": str(output_path),
        },
    )

    # Шаг 8: Загружаем результат как слой
    bedrock_banks_layer = QgsVectorLayer(str(output_path), "bedrock_banks", "ogr")

    print("Выделение коренных берегов завершено", flush=True)
    return bedrock_banks_layer


def _analyze_transects_for_bedrock(
    points_layer: QgsVectorLayer,
    rivers_layer: QgsVectorLayer,
    height_threshold: float,
    slope_threshold: float,
    min_consecutive: int,
    point_spacing: float,
) -> list:
    """
    Анализирует точки на каждом поперечном профиле для поиска коренных берегов.

    Returns:
        list: Список словарей с информацией о точках коренных берегов
    """
    # Получаем геометрию реки для расчета расстояний
    river_geom = None
    for feat in rivers_layer.getFeatures():
        if river_geom is None:
            river_geom = feat.geometry()
        else:
            river_geom = river_geom.combine(feat.geometry())
    
    if river_geom is None:
        return []
    bedrock_points = []

    # Группируем точки по профилям (используем несколько полей для надежности)
    profiles = {}
    for feature in points_layer.getFeatures():
        # Пробуем разные поля для идентификации профиля
        profile_id = feature.attribute("TR_ID")
        if profile_id is None:
            profile_id = feature.attribute("TR_SEGMENT")
        if profile_id is None:
            profile_id = feature.attribute("fid")
        if profile_id is None:
            profile_id = feature.id()  # последний резерв

        if profile_id not in profiles:
            profiles[profile_id] = []

        geom = feature.geometry()
        point = geom.asPoint()
        elevation = feature.attribute("elev_1")

        if elevation is None or elevation == -9999:  # NODATA
            continue

        profiles[profile_id].append(
            {
                "point": point,
                "elevation": elevation,
                "distance": feature.attribute("distance"),
                "profile_id": profile_id,
            }
        )

    # Анализируем каждый профиль
    for profile_id, profile_points in profiles.items():
        if len(profile_points) < min_consecutive + 1:
            continue

        # Сортируем точки по расстоянию вдоль профиля
        profile_points.sort(key=lambda p: p["distance"])

        # Определяем точку русла - ближайшая к линии реки
        if river_geom:
            min_dist = float('inf')
            river_idx = len(profile_points) // 2  # fallback
            for idx, p in enumerate(profile_points):
                point_geom = QgsGeometry.fromPointXY(QgsPointXY(p["point"]))
                dist = point_geom.distance(river_geom)
                if dist < min_dist:
                    min_dist = dist
                    river_idx = idx
        else:
            river_idx = len(profile_points) // 2
        
        river_point = profile_points[river_idx]
        river_elevation = river_point["elevation"]

        # Вычисляем расстояние вдоль реки для этого профиля
        river_distance = 0
        if river_geom:
            point_geom = QgsGeometry.fromPointXY(QgsPointXY(river_point["point"]))
            river_distance = river_geom.lineLocatePoint(point_geom)

        # Анализируем левый берег (от русла влево)
        left_bedrock = _find_bedrock_on_side(
            profile_points[:river_idx][::-1],  # от русла наружу
            river_elevation,
            height_threshold,
            slope_threshold,
            min_consecutive,
            point_spacing,
            "left",
            profile_id,
            river_distance,
        )

        if left_bedrock:
            bedrock_points.append(left_bedrock)

        # Анализируем правый берег (от русла вправо)
        right_bedrock = _find_bedrock_on_side(
            profile_points[river_idx + 1 :],
            river_elevation,
            height_threshold,
            slope_threshold,
            min_consecutive,
            point_spacing,
            "right",
            profile_id,
            river_distance,
        )

        if right_bedrock:
            bedrock_points.append(right_bedrock)

    return bedrock_points


def _find_bedrock_on_side(
    points: list,
    river_elevation: float,
    height_threshold: float,
    slope_threshold: float,
    min_consecutive: int,
    point_spacing: float,
    side: str,
    profile_id: int,
    river_distance: float = 0.0,
):
    """
    Находит точку коренного берега на одной стороне профиля.

    Args:
        points: Список точек от русла наружу
        river_elevation: Высота точки в русле
        height_threshold: Минимальный подъем
        slope_threshold: Минимальный уклон
        min_consecutive: Количество последовательных точек
        point_spacing: Расстояние между точками
        side: "left" или "right"
        profile_id: ID профиля
        river_distance: Расстояние вдоль реки для сортировки

    Returns:
        dict: Информация о точке коренного берега или None
    """
    for i in range(len(points) - min_consecutive + 1):
        current = points[i]
        height_diff = current["elevation"] - river_elevation

        # Проверка критерия высоты
        if height_diff < height_threshold:
            continue

        # Проверка критерия уклона (между предыдущей и текущей точкой)
        if i > 0:
            prev = points[i - 1]
            elevation_change = current["elevation"] - prev["elevation"]
            slope_degrees = math.degrees(math.atan(elevation_change / point_spacing))

            if slope_degrees < slope_threshold:
                continue

        # Проверка устойчивости: следующие точки тоже должны быть выше порога
        is_stable = True
        for j in range(1, min_consecutive):
            if i + j >= len(points):
                is_stable = False
                break

            next_point = points[i + j]
            next_height_diff = next_point["elevation"] - river_elevation

            if next_height_diff < height_threshold:
                is_stable = False
                break

        if is_stable:
            # Нашли точку коренного берега
            return {
                "point": current["point"],
                "elevation": current["elevation"],
                "height_diff": height_diff,
                "side": side,
                "profile_id": profile_id,
                "distance_along": river_distance,  # расстояние вдоль реки, не профиля
            }

    return None


def _create_points_layer(bedrock_points: list) -> QgsVectorLayer:
    """
    Создает векторный слой из списка точек коренных берегов.
    """
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "bedrock_points", "memory")
    provider = layer.dataProvider()

    # Добавляем поля
    provider.addAttributes(
        [
            QgsField("elevation", QVariant.Double),
            QgsField("height_diff", QVariant.Double),
            QgsField("side", QVariant.String),
            QgsField("profile_id", QVariant.Int),
            QgsField("distance_along", QVariant.Double),
        ]
    )
    layer.updateFields()

    # Добавляем точки
    features = []
    for point_data in bedrock_points:
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point_data["point"])))
        feature.setAttributes(
            [
                point_data["elevation"],
                point_data["height_diff"],
                point_data["side"],
                point_data["profile_id"],
                point_data["distance_along"],
            ]
        )
        features.append(feature)

    provider.addFeatures(features)
    layer.updateExtents()

    return layer
