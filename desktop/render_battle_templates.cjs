// Offline derivative templates. Original model database and previews stay intact.
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'..'),base=path.join(root,'outputs/regulation_battle_models_2026-11-13');
 const rows=JSON.parse(fs.readFileSync(path.join(root,'sources/spine/models_analyzed.json'),'utf8'));
 const dir=path.join(__dirname,'build/battle-templates');fs.mkdirSync(dir,{recursive:true});
 const browser=await chromium.launch({executablePath:'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',headless:true,args:['--enable-unsafe-swiftshader']});
 const manifest=[];
 try{
  const page=await browser.newPage();await page.setContent('<canvas id="c" width="256" height="256"></canvas>');
  await page.addScriptTag({content:fs.readFileSync(path.join(root,'sources/spine/runtime_internal.js'),'utf8')});
  for(const row of rows){
   const assets=row.files.map(f=>({name:f.filename,kind:f.kind,data:fs.readFileSync(path.join(base,f.relative_path)).toString('base64')}));
   const frames=await page.evaluate(async assets=>{
    const S=window.spine,canvas=document.getElementById('c');
    const gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:false,preserveDrawingBuffer:true});
    const shader=S.webgl.Shader.newTwoColoredTextured(gl),batcher=new S.webgl.PolygonBatcher(gl),renderer=new S.webgl.SkeletonRenderer(gl),mvp=new S.webgl.Matrix4();
    renderer.premultipliedAlpha=true;
    const textures={};for(const a of assets.filter(a=>a.kind==='texture')){
     const image=new Image();image.src='data:image/png;base64,'+a.data;await image.decode();textures[a.name]=new S.webgl.GLTexture(gl,image);
    }
    const text=a=>new TextDecoder().decode(Uint8Array.from(atob(a.data),x=>x.charCodeAt(0)));
    const atlas=new S.TextureAtlas(text(assets.find(a=>a.kind==='atlas')),name=>textures[name]);
    const bytes=Uint8Array.from(atob(assets.find(a=>a.kind==='skeleton').data),x=>x.charCodeAt(0));
    const loader=new S.AtlasAttachmentLoader(atlas),isJson=/^\s*\{/.test(new TextDecoder().decode(bytes.slice(0,50)));
    const data=isJson?new S.SkeletonJson(loader).readSkeletonData(new TextDecoder().decode(bytes)):new S.SkeletonBinary(loader).readSkeletonData(bytes);
    const anims=data.animations.filter(a=>/idle/i.test(a.name));
    if(!anims.length)anims.push(data.animations.find(a=>/^Default$/i.test(a.name))||data.animations[0]);
    const out=[];
    for(const anim of anims){
     for(const phase of /^idle$/i.test(anim.name)?[.05,.35,.7]:[.35]){
      const skeleton=new S.Skeleton(data),t=anim.duration*phase;
      skeleton.setToSetupPose();anim.apply(skeleton,-1,t,false,[],1,S.MixBlend.setup,S.MixDirection.mixIn);skeleton.updateWorldTransform();
      let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;const verts=[];
      for(const slot of skeleton.drawOrder){
       if(!slot.bone.active||slot.color.a<.02)continue;
       const a=slot.getAttachment();let count=0;
       if(a instanceof S.RegionAttachment){if(a.color.a<.02)continue;count=8;verts.length=count;a.computeWorldVertices(slot.bone,verts,0,2);}
       else if(a instanceof S.MeshAttachment){if(a.color.a<.02)continue;count=a.worldVerticesLength;verts.length=count;a.computeWorldVertices(slot,0,count,verts,0,2);}
       for(let j=0;j<count;j+=2){x0=Math.min(x0,verts[j]);x1=Math.max(x1,verts[j]);y0=Math.min(y0,verts[j+1]);y1=Math.max(y1,verts[j+1]);}
      }
      if(!Number.isFinite(x0)||x1<=x0||y1<=y0)continue;
      const extent=Math.max(x1-x0,y1-y0)*1.16,cx=(x1+x0)/2,cy=(y1+y0)/2;
      mvp.ortho2d(cx-extent/2,cy-extent/2,extent,extent);gl.viewport(0,0,256,256);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
      shader.bind();shader.setUniformi(S.webgl.Shader.SAMPLER,0);shader.setUniform4x4f(S.webgl.Shader.MVP_MATRIX,mvp.values);
      batcher.begin(shader);renderer.draw(batcher,skeleton);batcher.end();shader.unbind();
      out.push({animation:anim.name,time:t,png:canvas.toDataURL('image/png')});
     }
    }
    atlas.dispose();shader.dispose();batcher.dispose();return out;
   },assets);
   for(let i=0;i<frames.length;i++){
    const f=frames[i],file=row.model_id+'-'+i+'.png';fs.writeFileSync(path.join(dir,file),Buffer.from(f.png.split(',')[1],'base64'));
    manifest.push({model_id:row.model_id,operator_id:row.operator_id,direction:row.model_id.split('-')[1],animation:f.animation,time:f.time,file});
   }
   if(manifest.length%50<frames.length)console.log(manifest.length+' templates rendered');
  }
  fs.writeFileSync(path.join(dir,'manifest.json'),JSON.stringify(manifest,null,2));console.log('DONE '+manifest.length);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
