from PIL import Image
from .workspace import atomic_json
from .upstream_adapter import make_blind_composite

def compare(reference,candidate,output):
    meta=make_blind_composite(reference,candidate,output)
    atomic_json(output.with_suffix('.json'),meta)
    return meta

def crop(source,request,output):
    with Image.open(source) as im:
        x,y,w,h=request.bbox
        box=(int(x*im.width),int(y*im.height),max(int((x+w)*im.width),int(x*im.width)+1),max(int((y+h)*im.height),int(y*im.height)+1))
        part=im.crop(box);scale=min(request.scale,4096/max(part.size))
        size=tuple(max(1,round(v*scale)) for v in part.size)
        part.resize(size,Image.Resampling.LANCZOS).save(output)
    atomic_json(output.with_suffix('.json'),{'source_bbox':request.bbox,'pixel_crop':box,'scale':scale,'source':str(source)})
