(function (root) {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const EARTH_RADIUS_M = 6371008.8;

  function finite(value) {
    return typeof value === 'number' && Number.isFinite(value);
  }

  function isHttpUrl(value) {
    if (typeof value !== 'string') return false;
    try {
      return new URL(value).protocol === 'https:';
    } catch {
      return false;
    }
  }

  function signedAngle(angle) {
    return ((angle + 180) % 360 + 360) % 360 - 180;
  }

  function haversineMeters(pointA, pointB) {
    const toRadians = (degrees) => degrees * Math.PI / 180;
    const latitudeA = toRadians(pointA.latitude);
    const latitudeB = toRadians(pointB.latitude);
    const deltaLatitude = latitudeB - latitudeA;
    const deltaLongitude = toRadians(pointB.longitude - pointA.longitude);
    const value = Math.sin(deltaLatitude / 2) ** 2 +
      Math.cos(latitudeA) * Math.cos(latitudeB) *
      Math.sin(deltaLongitude / 2) ** 2;
    return 2 * EARTH_RADIUS_M *
      Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  }

  function bearingDegrees(pointA, pointB) {
    const toRadians = (degrees) => degrees * Math.PI / 180;
    const latitudeA = toRadians(pointA.latitude);
    const latitudeB = toRadians(pointB.latitude);
    const deltaLongitude = toRadians(pointB.longitude - pointA.longitude);
    const y = Math.sin(deltaLongitude) * Math.cos(latitudeB);
    const x = Math.cos(latitudeA) * Math.sin(latitudeB) -
      Math.sin(latitudeA) * Math.cos(latitudeB) * Math.cos(deltaLongitude);
    return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
  }

  function isVerifiedCameraMap(data) {
    if (
      !data ||
      data.status !== 'verified' ||
      data.coordinate_reference_system !== 'WGS84'
    ) return false;
    const stage = data.stage;
    if (
      !stage ||
      !finite(stage.latitude) ||
      !finite(stage.longitude) ||
      !finite(stage.horizontal_uncertainty_m) ||
      !finite(stage.ground_elevation_m) ||
      !finite(stage.front_azimuth_deg_true) ||
      !isHttpUrl(stage.source_url) ||
      typeof stage.vertical_datum !== 'string' ||
      !stage.vertical_datum.trim() ||
      stage.latitude < -90 ||
      stage.latitude > 90 ||
      stage.longitude < -180 ||
      stage.longitude > 180 ||
      stage.horizontal_uncertainty_m < 0 ||
      stage.front_azimuth_deg_true < 0 ||
      stage.front_azimuth_deg_true >= 360
    ) return false;
    return Array.isArray(data.cameras) && data.cameras.length > 0 &&
      data.cameras.every((camera) =>
        camera &&
        typeof camera.id === 'string' &&
        finite(camera.latitude) &&
        finite(camera.longitude) &&
        finite(camera.horizontal_uncertainty_m) &&
        finite(camera.ground_elevation_m) &&
        finite(camera.lens_height_agl_m) &&
        finite(camera.camera_to_stage_distance_m) &&
        finite(camera.aim_azimuth_deg_true) &&
        finite(camera.relative_azimuth_deg) &&
        finite(camera.aim_pitch_deg) &&
        isHttpUrl(camera.source_url) &&
        typeof camera.source_timestamp === 'string' &&
        typeof camera.evidence_notes === 'string' &&
        camera.latitude >= -90 &&
        camera.latitude <= 90 &&
        camera.longitude >= -180 &&
        camera.longitude <= 180 &&
        camera.horizontal_uncertainty_m >= 0 &&
        camera.lens_height_agl_m >= 0 &&
        camera.camera_to_stage_distance_m >= 0 &&
        camera.aim_azimuth_deg_true >= 0 &&
        camera.aim_azimuth_deg_true < 360 &&
        camera.relative_azimuth_deg >= -180 &&
        camera.relative_azimuth_deg <= 180 &&
        camera.aim_pitch_deg >= -90 &&
        camera.aim_pitch_deg <= 90 &&
        typeof camera.vertical_datum === 'string' &&
        camera.vertical_datum.trim() !== '' &&
        Math.abs(
          camera.camera_to_stage_distance_m -
          haversineMeters(camera, stage),
        ) <= Math.max(
          2,
          camera.horizontal_uncertainty_m + stage.horizontal_uncertainty_m,
        ) &&
        Math.abs(
          signedAngle(
            camera.relative_azimuth_deg -
            (bearingDegrees(stage, camera) - stage.front_azimuth_deg_true),
          ),
        ) <= 5 &&
        Math.abs(
          signedAngle(
            camera.aim_azimuth_deg_true -
            bearingDegrees(camera, stage),
          ),
        ) <= 5,
        );
  }

  function projectToLocalMeters(latitude, longitude, origin) {
    const latitudeRadians = origin.latitude * Math.PI / 180;
    return {
      east: (longitude - origin.longitude) * Math.PI / 180 *
        EARTH_RADIUS_M * Math.cos(latitudeRadians),
      north: (latitude - origin.latitude) * Math.PI / 180 * EARTH_RADIUS_M,
    };
  }

  function projectScene(data, width, height) {
    const stage = data.stage;
    const points = [
      {
        id: 'STAGE',
        label: '舞台',
        ...projectToLocalMeters(stage.latitude, stage.longitude, stage),
        z: 0,
      },
      ...data.cameras.map((camera) => {
        const local = projectToLocalMeters(
          camera.latitude,
          camera.longitude,
          stage,
        );
        return {
          id: camera.id,
          label: camera.label || camera.id,
          ...local,
          z: camera.ground_elevation_m - stage.ground_elevation_m +
            camera.lens_height_agl_m,
        };
      }),
    ].map((point) => ({
      ...point,
      x: point.east - point.north,
      y: (point.east + point.north) * 0.5 - point.z,
    }));
    const margin = 48;
    const minX = Math.min(...points.map((point) => point.x));
    const maxX = Math.max(...points.map((point) => point.x));
    const minY = Math.min(...points.map((point) => point.y));
    const maxY = Math.max(...points.map((point) => point.y));
    const scale = Math.min(
      (width - margin * 2) / Math.max(maxX - minX, 1),
      (height - margin * 2) / Math.max(maxY - minY, 1),
    );
    return points.map((point) => ({
      ...point,
      screenX: margin + (point.x - minX) * scale,
      screenY: margin + (maxY - point.y) * scale,
    }));
  }

  function createSvgElement(name, attributes, text) {
    const element = root.document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) {
      element.setAttribute(key, String(value));
    }
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function renderCameraMap(data, scene, status, details) {
    scene.replaceChildren();
    details.replaceChildren();
    if (!isVerifiedCameraMap(data)) {
      status.textContent = '机位测绘未核实；未绘制推测坐标。';
      const note = root.document.createElement('p');
      note.className = 'camera-map-unavailable';
      note.textContent = '待补：舞台坐标与方向、每个公开媒体机位的坐标和误差、镜头高度、拍摄俯仰角、距离及来源证据。';
      scene.append(note);
      return;
    }

    const width = 720;
    const height = 360;
    const projected = projectScene(data, width, height);
    const stage = projected[0];
    const svg = createSvgElement('svg', {
      viewBox: `0 0 ${width} ${height}`,
      role: 'img',
      'aria-label': `${data.event_title} 的三维机位示意图`,
    });
    for (const camera of projected.slice(1)) {
      svg.append(createSvgElement('line', {
        x1: camera.screenX,
        y1: camera.screenY,
        x2: stage.screenX,
        y2: stage.screenY,
        class: 'camera-map-sightline',
      }));
      svg.append(createSvgElement('circle', {
        cx: camera.screenX,
        cy: camera.screenY,
        r: 9,
        class: 'camera-map-camera',
      }));
      svg.append(createSvgElement('text', {
        x: camera.screenX + 12,
        y: camera.screenY - 8,
        class: 'camera-map-label',
      }, camera.label));
    }
    const stageEast = Math.sin(
      data.stage.front_azimuth_deg_true * Math.PI / 180,
    );
    const stageNorth = Math.cos(
      data.stage.front_azimuth_deg_true * Math.PI / 180,
    );
    const frontX = stageEast - stageNorth;
    const frontY = -(stageEast + stageNorth) * 0.5;
    const frontLength = Math.hypot(frontX, frontY) || 1;
    svg.append(createSvgElement('line', {
      x1: stage.screenX,
      y1: stage.screenY,
      x2: stage.screenX + frontX / frontLength * 38,
      y2: stage.screenY + frontY / frontLength * 38,
      class: 'camera-map-stage-axis',
      'marker-end': 'url(#camera-map-arrow)',
    }));
    const defs = createSvgElement('defs', {});
    const marker = createSvgElement('marker', {
      id: 'camera-map-arrow',
      viewBox: '0 0 10 10',
      refX: 8,
      refY: 5,
      markerWidth: 5,
      markerHeight: 5,
      orient: 'auto-start-reverse',
    });
    marker.append(createSvgElement('path', {
      d: 'M 0 0 L 10 5 L 0 10 z',
      class: 'camera-map-arrowhead',
    }));
    defs.append(marker);
    svg.prepend(defs);
    svg.append(createSvgElement('path', {
      d: `M ${stage.screenX} ${stage.screenY - 12} l 12 12 l -12 12 l -12 -12 z`,
      class: 'camera-map-stage',
    }));
    svg.append(createSvgElement('text', {
      x: stage.screenX + 14,
      y: stage.screenY + 5,
      class: 'camera-map-label',
    }, '舞台 / Z=0'));
    svg.append(createSvgElement('text', {
      x: stage.screenX + frontX / frontLength * 42,
      y: stage.screenY + frontY / frontLength * 42 - 6,
      class: 'camera-map-label',
    }, '舞台正面'));
    svg.append(createSvgElement('line', {
      x1: width - 54,
      y1: 68,
      x2: width - 82,
      y2: 54,
      class: 'camera-map-compass',
      'marker-end': 'url(#camera-map-arrow)',
    }));
    svg.append(createSvgElement('text', {
      x: width - 95,
      y: 50,
      class: 'camera-map-label',
    }, 'N'));
    svg.append(createSvgElement('line', {
      x1: width - 54,
      y1: 78,
      x2: width - 54,
      y2: 42,
      class: 'camera-map-height-axis',
      'marker-end': 'url(#camera-map-arrow)',
    }));
    svg.append(createSvgElement('text', {
      x: width - 48,
      y: 42,
      class: 'camera-map-label',
    }, '+Z'));
    scene.append(svg);
    status.textContent =
      `${data.cameras.length} 个有证据的媒体机位 · WGS84 · ` +
      `舞台正面 ${data.stage.front_azimuth_deg_true}° 真北 · 3D 示意`;

    const stageItem = root.document.createElement('li');
    stageItem.textContent =
      `舞台中心 · ${data.stage.latitude.toFixed(5)}, ${data.stage.longitude.toFixed(5)}` +
      ` · 坐标误差 ±${data.stage.horizontal_uncertainty_m}m` +
      ` · 地面高 ${data.stage.ground_elevation_m}m (${data.stage.vertical_datum})` +
      ` · 正面 ${data.stage.front_azimuth_deg_true}° 真北`;
    details.append(stageItem);

    for (const camera of data.cameras) {
      const item = root.document.createElement('li');
      item.textContent =
        `${camera.label || camera.id} · ${camera.latitude.toFixed(5)}, ${camera.longitude.toFixed(5)}` +
        ` · 坐标误差 ±${camera.horizontal_uncertainty_m}m` +
        ` · 距舞台 ${camera.camera_to_stage_distance_m}m` +
        ` · 方位 ${camera.aim_azimuth_deg_true}° 真北 / 相对舞台 ${camera.relative_azimuth_deg}°` +
        ` · 镜头高 ${camera.lens_height_agl_m}m / 俯仰 ${camera.aim_pitch_deg}°` +
        ` · 证据 ${camera.source_timestamp}`;
      details.append(item);
    }
  }

  const api = {
    bearingDegrees,
    haversineMeters,
    isVerifiedCameraMap,
    projectScene,
    projectToLocalMeters,
    signedAngle,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (!root.document) return;

  const scene = root.document.getElementById('cameraMapScene');
  const status = root.document.getElementById('cameraMapStatus');
  const details = root.document.getElementById('cameraMapDetails');
  if (!scene || !status || !details) return;
  root.fetch('./outputs/whitehouse-oct-06-2026/camera-map.json', {
    cache: 'no-store',
  })
    .then((response) => {
      if (!response.ok) throw new Error('Camera map data is unavailable.');
      return response.json();
    })
    .then((data) => renderCameraMap(data, scene, status, details))
    .catch((error) => {
      console.error(error);
      status.textContent = '机位测绘数据不可用';
      scene.textContent = '请勿依据空缺数据推测机位；需要补充经核实的测量与来源证据。';
    });
})(globalThis);
