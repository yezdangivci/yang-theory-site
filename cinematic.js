import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { FilmRenderer } from './film-renderer.js';

gsap.registerPlugin(ScrollTrigger);

const stage=document.getElementById('filmStage');
const canvas=document.getElementById('filmCanvas');
const loading=document.getElementById('filmLoading');
const retry=document.getElementById('filmRetry');
const header=document.getElementById('siteHeader');
const copy=document.getElementById('filmCopy');
const meta=document.querySelector('.film-meta');
const title=document.getElementById('filmTitle');
const type=document.getElementById('filmType');
const subtitle=document.getElementById('filmSubtitle');
const counter=document.getElementById('filmCounter');
const progressBar=document.getElementById('filmProgress');
const cta=document.getElementById('filmCta');
const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp=(v,lo=0,hi=1)=>Math.min(hi,Math.max(lo,v));

const assets=[
  {url:new URL('./zaru_3_web.mp4',import.meta.url).href,fps:24,start:0,end:.205,in:5,out:13.6},
  {url:new URL('./Journey:Yez Startle video.mp4',import.meta.url).href,fps:30,start:.13,end:.34,in:.75,out:4.8},
  {url:new URL('./seek_magic_table.png',import.meta.url).href},
  {url:new URL('./ophelia_landing_916_web.mp4',import.meta.url).href,fps:24,start:.425,end:.65,in:2,out:12.15},
  {url:new URL('./shila_lastvideo.mp4',import.meta.url).href,fps:30,start:.585,end:.8,in:.3,out:5.6},
  {url:new URL('./yez_ekran_final_web.mp4',import.meta.url).href,fps:24,start:.73,end:1,in:0,out:7},
];
const connections=[
  {start:.13,end:.205,from:0,to:1},
  {start:.275,end:.34,from:1,to:2},
  {start:.425,end:.49,from:2,to:3},
  {start:.585,end:.65,from:3,to:4},
  {start:.73,end:.8,from:4,to:5},
];
const texts=[
  ['01 — Wearable art','Zaru','A handmade artifact. A world within the stone.'],
  ['02 — Original story world','Journey','The forest answers when curiosity reaches out.'],
  ['03 — Material experiments','Seek Magic','Color, crystal and a universe on a tabletop.'],
  ['04 — Wearable art','Ophelia','Sculpted by hand. Defined by a red stone.'],
  ['05 — Hand-painted objects','Shila','The timeless queen. An everyday object reimagined.'],
  ['06 — Journey films','Burton','The guide takes flight.'],
];

let renderer;
let timeline;
let paintRequest=0;
let previousText='';
const playhead={progress:0};
const samplers=[];
const bin=document.createElement('div');bin.className='film-media-bin';bin.setAttribute('aria-hidden','true');document.body.append(bin);

function queuePaint() {
  if (!paintRequest) paintRequest=requestAnimationFrame(()=>{paintRequest=0;paint();});
}

class VideoSampler {
  constructor(index,asset) {
    this.index=index;this.asset=asset;this.desired=asset.in;this.presented=-1;this.busy=false;this.ready=false;
    this.listeners=new Set();
    const video=document.createElement('video');this.video=video;
    video.dataset.filmSource=String(index);video.muted=true;video.playsInline=true;video.preload='auto';video.disablePictureInPicture=true;
    video.setAttribute('playsinline','');video.src=asset.url;bin.append(video);
    video.addEventListener('seeked',()=>this.finish());
    video.addEventListener('error',()=>this.fail(new Error(`Unable to load ${new URL(asset.url).pathname}`)));
  }
  load() {
    return new Promise((resolve,reject)=>{
      this.reject=reject;
      const timer=setTimeout(()=>reject(new Error('Video loading timed out')),30000);
      this.video.addEventListener('loadedmetadata',()=>{
        // Seeking also requests a decoded frame on browsers that initially
        // preload only metadata. Playback itself remains paused and scroll-bound.
        if(this.desired>0)this.video.currentTime=this.desired;
      },{once:true});
      this.video.addEventListener('loadeddata',()=>{
        clearTimeout(timer);this.ready=true;renderer.upload(this.index,this.video);this.seek(this.desired);resolve();
      },{once:true});
      this.video.load();
    });
  }
  fail(error) { if(this.reject)this.reject(error); }
  seek(time) {
    const {fps}=this.asset;
    this.desired=Math.round(clamp(time,0,Math.max(0,(this.video.duration||20)-1/fps))*fps)/fps;
    this.pump();
  }
  pump() {
    if(!this.ready||this.busy||Math.abs(this.presented-this.desired)<.45/this.asset.fps)return;
    if(Math.abs(this.video.currentTime-this.desired)<.001) { this.finish();return; }
    this.busy=true;
    this.video.currentTime=this.desired;
  }
  finish() {
    if(!this.ready||this.video.readyState<2)return;
    // seeked exposes the decoded target frame. Two rendering turns give WebKit
    // the same presentation opportunity without running a free-playing clock.
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      renderer.upload(this.index,this.video);this.presented=this.video.currentTime;this.video.dataset.frameTime=String(this.presented);this.busy=false;
      for(const listener of this.listeners)listener();
      queuePaint();this.pump();
    }));
  }
  waitForFrame() {
    if(Math.abs(this.presented-this.desired)<.45/this.asset.fps)return Promise.resolve();
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.listeners.delete(done);reject(new Error('Video decoding timed out'));},30000);
      const done=()=>{
        if(Math.abs(this.presented-this.desired)<.45/this.asset.fps){clearTimeout(timer);this.listeners.delete(done);resolve();}
      };
      this.listeners.add(done);
    });
  }
  at(progress) {
    const a=this.asset;
    return a.in+(a.out-a.in)*clamp((progress-a.start)/(a.end-a.start));
  }
}

function select(progress) {
  for(let i=0;i<connections.length;i++) {
    const c=connections[i];
    if(progress<c.start)return {a:c.from,b:c.from,t:0,edit:-1};
    if(progress<=c.end)return {a:c.from,b:c.to,t:(progress-c.start)/(c.end-c.start),edit:i};
  }
  return {a:5,b:5,t:0,edit:-1};
}

function updateCopy(selection,p) {
  const i=selection.edit<0?selection.a:selection.t>=.12?selection.b:selection.a;
  const maker=i===5&&samplers[5].at(p)>=3.8;
  const key=`${i}:${maker}`;
  if(key!==previousText) {
    const text=maker?['06 — Creative production','Behind the world','Every story begins with a maker.']:texts[i];
    [type.textContent,title.textContent,subtitle.textContent]=text;
    counter.textContent=`${String(i+1).padStart(2,'0')} / 06`;
    copy.classList.toggle('is-maker',maker);previousText=key;
  }
  const light=i===2||i===3||i===4;
  // Metadata changes early; contrast follows the actual field under the copy.
  let copyLight=selection.edit===1?selection.t>.40:selection.edit===4?selection.t<.72:light;
  if(renderer.w<600) {
    if(selection.edit===2)copyLight=selection.t<.33;
    else if(selection.edit===3)copyLight=selection.t>.40;
    else if(i===3)copyLight=false;
  }
  const headerLight=selection.edit===1?selection.t>.76:selection.edit===4?selection.t<.32:light;
  copy.classList.toggle('is-light',copyLight);meta.classList.toggle('is-light',copyLight);
  header.classList.toggle('film-light',headerLight&&ScrollTrigger.getById('yang-film')?.isActive);
  header.classList.toggle('in-film',Boolean(ScrollTrigger.getById('yang-film')?.isActive));
  cta.hidden=!(maker&&samplers[5].at(p)>=5.1);
  progressBar.style.transform=`scaleX(${p})`;
  stage.dataset.progress=p.toFixed(6);stage.dataset.scene=String(i);
}

function paint() {
  if(!renderer||!stage.classList.contains('is-ready'))return;
  const p=playhead.progress,selection=select(p);
  if(reduceMotion) {
    const i=selection.edit>=0&&selection.t>.5?selection.b:selection.a;
    renderer.render(i,i,0,-1,p);updateCopy({...selection,a:i,b:i,t:0,edit:-1},p);return;
  }
  for(const i of new Set([selection.a,selection.b])) {
    if(samplers[i])samplers[i].seek(samplers[i].at(p));
  }
  renderer.render(selection.a,selection.b,selection.t,selection.edit,p);
  updateCopy(selection,p);
}

function updateHeader() {
  const trigger=ScrollTrigger.getById('yang-film');
  header.classList.toggle('in-film',Boolean(trigger?.isActive));
  if(!trigger?.isActive)header.classList.remove('film-light');
  const journey=document.getElementById('journey');
  header.classList.toggle('on-light',Boolean(trigger&&!trigger.isActive&&scrollY>trigger.end&&scrollY<journey.offsetTop));
}

async function init() {
  try {
    renderer=new FilmRenderer(canvas);
    const image=new Image();image.decoding='async';
    const imageReady=new Promise((resolve,reject)=>{image.onload=()=>{renderer.upload(2,image);resolve();};image.onerror=()=>reject(new Error('Unable to load Seek Magic'));});
    image.src=assets[2].url;
    for(let i=0;i<assets.length;i++)if(i!==2)samplers[i]=new VideoSampler(i,assets[i]);
    await Promise.all([imageReady,...samplers.filter(Boolean).map(s=>s.load())]);
    if(reduceMotion) {
      const moments={0:8,1:3,3:6,4:1.8,5:6.5};
      for(const sampler of samplers.filter(Boolean))sampler.seek(moments[sampler.index]);
    }
    await Promise.all(samplers.filter(Boolean).map(s=>s.waitForFrame()));
    stage.classList.add('is-ready');loading.hidden=true;
    timeline=gsap.timeline({scrollTrigger:{
      id:'yang-film',trigger:'#film',pin:stage,start:'top top',
      end:()=>`+=${Math.max(3600,stage.clientHeight*6.2)}`,
      scrub:true,anticipatePin:1,invalidateOnRefresh:true,
      onUpdate:()=>{queuePaint();updateHeader();},onToggle:updateHeader,
    }}).fromTo(playhead,{progress:0},{progress:1,duration:1,ease:'none',onUpdate:queuePaint});
    paint();ScrollTrigger.refresh();
    document.fonts.ready.then(()=>ScrollTrigger.refresh());
    let resizeRequest=0;
    const resize=()=>{
      cancelAnimationFrame(resizeRequest);
      resizeRequest=requestAnimationFrame(()=>{
        const bounds=canvas.getBoundingClientRect();
        if(Math.abs(bounds.width-renderer.w)>.5||Math.abs(bounds.height-renderer.h)>.5||Math.max(devicePixelRatio||1,1)!==renderer.dpr){
          renderer.resize();ScrollTrigger.refresh();queuePaint();
        }
      });
    };
    window.addEventListener('resize',resize,{passive:true});
    window.addEventListener('scroll',updateHeader,{passive:true});
    window.addEventListener('pageshow',()=>{ScrollTrigger.refresh();queuePaint();});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)queuePaint();});
    canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();loading.hidden=false;loading.querySelector('small').textContent='Restoring the world';});
    canvas.addEventListener('webglcontextrestored',()=>{
      renderer=new FilmRenderer(canvas);renderer.upload(2,image);
      for(const sampler of samplers.filter(Boolean))if(sampler.video.readyState>=2)renderer.upload(sampler.index,sampler.video);
      loading.hidden=true;queuePaint();
    });
    window.addEventListener('pagehide',event=>{if(!event.persisted){timeline?.scrollTrigger?.kill();timeline?.kill();renderer?.destroy();}});
  } catch(error) {
    console.error('Yang Theory film:',error);
    stage.dataset.error=error.message;
    loading.querySelector('small').textContent='The film could not load. Please retry.';
    retry.hidden=false;
  }
}

retry.addEventListener('click',()=>location.reload());
init();
