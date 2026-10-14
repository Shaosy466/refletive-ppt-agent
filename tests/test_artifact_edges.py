from PIL import Image,ImageDraw
from pptbench_harness.native import NativeSlide
from eval_harness.pptx import validate_reconstruction_pptx,PptxError
import pytest

def base():
    s=NativeSlide();s.rect('A',[.1,.3,.2,.2],'Alpha');s.rect('B',[.6,.3,.2,.2],'Beta');s.edge('edge',[(.3,.4),(.6,.4)])
    return s

def test_required_asset_missing(tmp_path):
    s=base();p=tmp_path/'candidate.pptx';s.save(p,tmp_path/'map.json')
    asset=tmp_path/'approved.png';Image.new('RGB',(40,40),'blue').save(asset)
    with pytest.raises(PptxError,match='(?i)resource'):
        validate_reconstruction_pptx(p,approved_resource_paths=[asset])

def test_unapproved_reference_copy(tmp_path):
    image=Image.new('RGB',(600,300),'white');d=ImageDraw.Draw(image)
    d.rectangle((30,60,180,160),fill='blue');d.rectangle((400,100,580,220),fill='orange');d.line((180,100,400,170),fill='black',width=5)
    ref=tmp_path/'reference.png';image.save(ref)
    s=base();s.slide.shapes.add_picture(str(ref),0,0,width=s.prs.slide_width,height=s.prs.slide_height)
    p=tmp_path/'copy.pptx';s.save(p,tmp_path/'map.json')
    with pytest.raises(PptxError):validate_reconstruction_pptx(p,reference_path=ref,approved_resource_paths=[])

def test_object_map_ids_are_verified(tmp_path):
    import json
    from pptbench_harness.validator import verify_object_map
    s=base();p=tmp_path/'candidate.pptx';m=tmp_path/'map.json';s.save(p,m)
    assert verify_object_map(p,m)['actual_shapes']==3
    rows=json.loads(m.read_text());rows[0]['pptx_shape_id']=999999;m.write_text(json.dumps(rows))
    with pytest.raises(PptxError,match='nonexistent'):verify_object_map(p,m)
