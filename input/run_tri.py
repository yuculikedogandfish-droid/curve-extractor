import seed_browser_use as bu, time, json, base64, sys
VER='109'
bu.navigate(f"file:///H:/tool/curve-extractor/app.html?v={VER}");time.sleep(8)
bu.js("""
window.loadTriDataURL=function(view,dataURL){return new Promise((res,rej)=>{const img=new Image();
img.onload=()=>{try{const cv=document.createElement('canvas');cv.width=img.width;cv.height=img.height;const cx=cv.getContext('2d');cx.drawImage(img,0,0);const rgb=cx.getImageData(0,0,img.width,img.height);S.triRgb[view]=rgb;S.triImages[view]=img;const slot=document.querySelector('.tri-slot[data-view="'+view+'"]');if(slot){slot.classList.add('filled');slot.querySelector('.state').textContent=img.width+'x'+img.height;}if(view==='front'){S.image=img;S.imgW=img.width;S.imgH=img.height;S.rgb=rgb;S._refCanvas=null;const dd=rgb.data;let sum=0;for(let i=0;i<dd.length;i+=4)sum+=Math.max(dd[i],dd[i+1],dd[i+2])/255;S.invertMask=(sum/(dd.length/4))>0.5;drawCanvas('canvasOriginal',rgb);autoTuneThreshold();}res(1);}catch(e){rej(String(e));}};img.onerror=()=>rej('imgerr');img.src=dataURL;});};'ok'""")
bu.js("document.getElementById('modeTri').click();'t'")
base=r'H:\tool\curve-extractor\input\tri'
group=sys.argv[1]
files={'g1':[('front','g1_front.txt','image/png'),('side','g1_side.txt','image/png'),('top','g1_top.txt','image/png')],
       'g2':[('front','g2_front.txt','image/png'),('side','g2_side.txt','image/jpeg'),('top','g2_top.txt','image/jpeg')]}[group]
def load(view,path,mime):
    b64=open(path,encoding='utf-8-sig').read().strip();bu.js("window._c=[];")
    for i in range(0,len(b64),40000):bu.js("window._c.push('"+b64[i:i+40000]+"');")
    bu.js("(function(){const b=window._c.join('');window._c=[];window._d=null;window.loadTriDataURL('"+view+"','data:"+mime+";base64,'+b).then(v=>window._d=v,e=>window._d='E');return 1;})()");time.sleep(1.2)
for v,f,m in files: load(v,base+'\\'+f,m)
bu.js("extractAll();'go'")
for i in range(25):
    time.sleep(1);d=json.loads(bu.js("JSON.stringify({c:(S.smoothedCurves||[]).length,px:S.mask?S.mask.reduce((a,b)=>a+b,0):0})"))
    if d['c']>0:print("DONE",d);break
bu.js("const t=[...document.querySelectorAll('.view-tab')].find(t=>t.dataset.view==='3d');document.querySelectorAll('.view-tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view-pane').forEach(p=>p.classList.remove('active'));t.classList.add('active');document.getElementById('pane-3d').classList.add('active');draw3DView();'o'")
time.sleep(2)
for cid,nm in [('canvasMask',f'_{group}_mask.png'),('canvas3d',f'_{group}_3d.png')]:
    u=bu.js("document.getElementById('"+cid+"').toDataURL('image/png')");open(base+'\\'+nm,'wb').write(base64.b64decode(u.split(',',1)[1]))
print("exported",group)
