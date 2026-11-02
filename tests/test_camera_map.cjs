const assert = require('node:assert/strict');
const test = require('node:test');

const {
  isVerifiedCameraMap,
  projectScene,
} = require('../assets/camera-map.js');

const verifiedMap = {
  status: 'verified',
  coordinate_reference_system: 'WGS84',
  stage: {
    latitude: 39.2,
    longitude: -76.4,
    horizontal_uncertainty_m: 2,
    ground_elevation_m: 5,
    vertical_datum: 'WGS84 ellipsoidal',
    front_azimuth_deg_true: 90,
    source_url: 'https://example.org/event-map',
  },
  cameras: [{
    id: 'media-a',
    label: 'Media A',
    latitude: 39.2001,
    longitude: -76.4,
    horizontal_uncertainty_m: 3,
    ground_elevation_m: 5,
    vertical_datum: 'WGS84 ellipsoidal',
    lens_height_agl_m: 2,
    camera_to_stage_distance_m: 11.12,
    aim_azimuth_deg_true: 180,
    relative_azimuth_deg: -90,
    aim_pitch_deg: -5,
    source_url: 'https://example.org/video',
    source_timestamp: '00:01:20',
    evidence_notes: 'Tripod at the public press riser.',
  }],
};

test('withholds unverified or incomplete camera coordinates', () => {
  assert.equal(isVerifiedCameraMap({ ...verifiedMap, status: 'not_verified' }), false);
  assert.equal(isVerifiedCameraMap({
    ...verifiedMap,
    cameras: [{ ...verifiedMap.cameras[0], horizontal_uncertainty_m: null }],
  }), false);
});

test('accepts fully evidenced WGS84 station records', () => {
  assert.equal(isVerifiedCameraMap(verifiedMap), true);
});

test('projects stage and camera into an isometric scene', () => {
  const projected = projectScene(verifiedMap, 720, 360);
  assert.equal(projected.length, 2);
  assert.notEqual(projected[0].screenX, projected[1].screenX);
  assert.ok(Number.isFinite(projected[1].screenY));
});
