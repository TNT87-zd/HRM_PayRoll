"""Compare preprocessing policies on separate enrollment/calibration/test captures.

Manifest JSONL rows:
{"path":"face.jpg","employee_id":"NV0001","capture_id":"session-1","split":"enroll","pose":"front"}
Use employee_id=null for unknown people. Enrollment requires two images per pose;
calibration/test captures require 3–5 frames each, like the kiosk. This script
writes a report; it never changes production configuration or employee data.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'app/backend/src'))
from config import POSES
from cv.face_engine import FaceEngine
from cv.matching import l2_normalize
from cv.preprocessing import POLICIES, enhance_face


def read_manifest(path):
    rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows or {row['split'] for row in rows}!={'enroll','calibration','test'}:
        raise ValueError('Manifest must contain enroll, calibration and test splits')
    seen_captures,seen_images={},{}
    groups=defaultdict(list)
    for row in rows:
        if row['split'] not in {'enroll','calibration','test'} or not row.get('capture_id'):
            raise ValueError('Invalid split/capture_id')
        row['path']=(path.parent/row['path']).resolve()
        digest=hashlib.sha256(row['path'].read_bytes()).hexdigest()
        capture=row['capture_id']; split=row['split']
        if capture in seen_captures and seen_captures[capture]!=split:
            raise ValueError('A capture_id cannot span different splits')
        if digest in seen_images:
            raise ValueError('Duplicate images are not independent samples')
        seen_captures[capture]=split;seen_images[digest]=split
        groups[(split,capture)].append(row)
    enrolled={row['employee_id'] for row in rows if row['split']=='enroll'}
    if None in enrolled: raise ValueError('Enrollment needs an employee_id')
    for employee in enrolled:
        counts=Counter(row.get('pose') for row in rows if row['split']=='enroll' and row['employee_id']==employee)
        if any(counts[p]!=2 for p in POSES) or sum(counts.values())!=10:
            raise ValueError('Enrollment needs two real images per pose for each employee')
    for (split,_),capture in groups.items():
        if len({row['employee_id'] for row in capture})!=1:
            raise ValueError('A capture must have one ground-truth identity')
        if split!='enroll' and not 3<=len(capture)<=5:
            raise ValueError('Calibration/test captures need 3–5 frames')
        if split!='enroll' and capture[0]['employee_id'] is not None and capture[0]['employee_id'] not in enrolled:
            raise ValueError('Use employee_id=null for a person who is not enrolled')
    for split in ('calibration','test'):
        identities=[r['employee_id'] for r in rows if r['split']==split]
        if None not in identities or not any(i is not None for i in identities):
            raise ValueError('Each evaluation split needs both known and unknown people')
    return rows,groups


def extract_all(rows,engine):
    aligned={}
    for row in rows:
        path=str(row['path'])
        face,report=engine.extract_single_face(path,require_single_face=True,check_quality=True,
                                             allow_pose_variation=row['split']=='enroll',min_secondary_face_area_ratio=0)
        aligned[path]=face.aligned_face if face is not None and report.is_valid else None
    return aligned


def score_captures(rows,groups,aligned,engine,policy,split):
    embeddings={path:(l2_normalize(engine.recognizer.get_embedding(enhance_face(image,policy))) if image is not None else None)
                for path,image in aligned.items()}
    gallery={}
    for employee in {row['employee_id'] for row in rows if row['split']=='enroll'}:
        vectors=[embeddings[str(row['path'])] for row in rows if row['split']=='enroll' and row['employee_id']==employee]
        if any(v is None for v in vectors): raise ValueError(f'Invalid enrollment image for {employee}; collect again')
        vectors=np.vstack(vectors);gallery[employee]=np.vstack([l2_normalize(vectors.mean(axis=0)),vectors])
    scored=[]
    for (group_split,capture_id),capture in groups.items():
        if group_split!=split: continue
        frame_scores=[]
        for row in capture:
            query=embeddings[str(row['path'])]
            if query is None: frame_scores=[];break
            ranked=sorted([(employee,float(np.max(vectors@query))) for employee,vectors in gallery.items()],key=lambda x:x[1],reverse=True)
            frame_scores.append((ranked[0][0],ranked[0][1],ranked[0][1]-ranked[1][1] if len(ranked)>1 else 2.0))
        valid=bool(frame_scores) and len({score[0] for score in frame_scores})==1
        scored.append({'capture_id':capture_id,'truth':capture[0]['employee_id'],
                       'candidate':frame_scores[0][0] if valid else None,
                       'score':min(score[1] for score in frame_scores) if valid else -1,
                       'margin':min(score[2] for score in frame_scores) if valid else -1})
    return scored


def metrics(captures,threshold,margin):
    counts=Counter()
    for capture in captures:
        truth=capture['truth'];known=truth is not None
        counts['known_attempts' if known else 'unknown_attempts']+=1
        accepted=capture['candidate'] is not None and capture['score']>=threshold and capture['margin']>=margin
        if known:
            counts['correct_known' if accepted and capture['candidate']==truth else 'wrong_identity' if accepted else 'rejected_known']+=1
        else: counts['accepted_unknown' if accepted else 'rejected_unknown']+=1
    result={key:counts[key] for key in ('known_attempts','unknown_attempts','correct_known','wrong_identity','rejected_known','accepted_unknown','rejected_unknown')}
    result['known_accept_rate']=counts['correct_known']/max(1,counts['known_attempts'])
    result['total_attempts']=len(captures)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows,groups=read_manifest(args.manifest.resolve())
    engine=FaceEngine(auto_download=False,providers=['CPUExecutionProvider'])
    aligned=extract_all(rows,engine)
    candidates=[]
    for policy in POLICIES:
        scored=score_captures(rows,groups,aligned,engine,policy,'calibration')
        for threshold in np.arange(.45,.86,.01):
            for margin in (.04,.08,.12,.16):
                result=metrics(scored,float(threshold),margin)
                candidates.append({'policy':policy,'threshold':round(float(threshold),2),'min_margin':margin,'calibration':result})
    candidates.sort(key=lambda c:(c['calibration']['wrong_identity']+c['calibration']['accepted_unknown'],
                                  -c['calibration']['correct_known'],POLICIES.index(c['policy']),-c['threshold'],-c['min_margin']))
    selected=candidates[0]
    selected['test']=metrics(score_captures(rows,groups,aligned,engine,selected['policy'],'test'),selected['threshold'],selected['min_margin'])
    baseline=next(c for c in candidates if c['policy']=='baseline').copy()
    baseline['test']=metrics(score_captures(rows,groups,aligned,engine,'baseline','test'),baseline['threshold'],baseline['min_margin'])
    summary={policy:next(c for c in candidates if c['policy']==policy) for policy in POLICIES}
    report={'selected_from':'calibration_only','selected':selected,'baseline':baseline,'calibration_by_policy':summary,
            'recognizer_sha256':hashlib.sha256(Path(engine.rec_model_path).read_bytes()).hexdigest(),
            'production_changed':False,'warning':'Finite held-out results do not guarantee 100% accuracy. Review the report before changing model policy/thresholds and rebuild templates.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'selected_policy':selected['policy'],'test':selected['test'],'report':str(args.output)},ensure_ascii=False))


if __name__=='__main__': main()
