import test from 'node:test';
import assert from 'node:assert/strict';
import {anglesFromMatrix, classifyPose, bestPair, diverse} from '../js/face-capture-core.mjs';

const candidate = (score, time, value, yaw = 0) => ({score, captured_at: time, fingerprint: [value, value],
  absolute: {yaw, pitch: 0, roll: 0}, angles: {yaw, pitch: 0, roll: 0}, sample_id: `${time}-${value}`});

test('directions and limits match server rules', () => {
  assert.equal(classifyPose({yaw:22,pitch:0,roll:0}), 'left');
  assert.equal(classifyPose({yaw:-22,pitch:0,roll:0}), 'right');
  assert.equal(classifyPose({yaw:0,pitch:15,roll:0}), 'down');
  assert.equal(classifyPose({yaw:0,pitch:-15,roll:0}), 'up');
  assert.equal(classifyPose({yaw:35,pitch:0,roll:0}), null);
  assert.equal(classifyPose({yaw:0,pitch:0,roll:14}), null);
});

test('column-major matrix gives same yaw as server row-major matrix', () => {
  const a=20*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
  const result=anglesFromMatrix([c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,-50,1]);
  assert.ok(Math.abs(result.yaw-20)<1e-8);
});

test('best pair selects quality while enforcing time and diversity', () => {
  const a=candidate(.9,1,10),b=candidate(.99,1.1,20),c=candidate(.8,1.5,30);
  assert.equal(diverse(a,b),false);
  const pair=bestPair([a,b,c],'front');
  assert.ok(pair.includes(b)); assert.ok(pair.includes(c));
  assert.equal(bestPair([candidate(.9,1,10),candidate(.8,2,10)],'front'),null);
});

test('accepted server sample is preserved when collecting a replacement', () => {
  const locked=candidate(.5,1,10),b=candidate(.99,2,20),c=candidate(.98,3,30);
  const pair=bestPair([b,c],'left',[locked]);
  assert.ok(pair.includes(locked)); assert.ok(pair.includes(b));
});

test('frontal pair must share a valid baseline', () => {
  assert.equal(bestPair([candidate(.9,1,10,-9),candidate(.8,2,30,9)],'front'),null);
});
