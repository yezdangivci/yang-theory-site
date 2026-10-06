import { vertexShader, fragmentShader } from './film-shaders.js';

const sizes = [[1964,1080],[1918,1080],[1255,1263],[1080,1920],[1090,1080],[1920,1080]];
const crops = [[0,0,1,1],[0,0,1,1],[644/2500,81/1406,1255/2500,1263/1406],[0,0,1,1],[420/1920,0,1090/1920,1],[0,0,1,1]];

function rectFor(i,w,h,dpr) {
  const mobile = w < 600;
  let maxW=w, maxH=h, cx=w*.5, cy=h*.47;
  if (i===0) { maxW=w*(mobile?.99:.78);maxH=h*(mobile?.55:.78);cx=w*(mobile?.5:.55);cy=h*(mobile?.36:.45); }
  if (i===1 || i===5) { maxW=w;maxH=h;cy=h*.5; }
  if (i===2) { maxW=w*(mobile?.88:.60);maxH=h*(mobile?.52:.73);cx=w*(mobile?.5:.59);cy=h*(mobile?.37:.46); }
  if (i===3) { maxW=w*(mobile?.72:.40);maxH=Math.min(h*(mobile?.66:.84),820);cx=w*(mobile?.5:.62);cy=h*(mobile?.36:.47); }
  if (i===4) { maxW=w*(mobile?.79:.46);maxH=Math.min(h*(mobile?.48:.65),520);cx=w*(mobile?.5:.59);cy=h*(mobile?.35:.45); }
  // Size to actual source pixels at device resolution, with no anamorphic scaling.
  const [sw,sh]=sizes[i];
  const scale=Math.min(maxW/sw,maxH/sh,1/dpr);
  const rw=sw*scale,rh=sh*scale;
  return [(cx-rw/2)/w,(cy-rh/2)/h,rw/w,rh/h];
}

export class FilmRenderer {
  constructor(canvas) {
    this.canvas=canvas;
    this.gl=canvas.getContext('webgl',{alpha:false,antialias:false,premultipliedAlpha:false,preserveDrawingBuffer:true});
    if (!this.gl) throw new Error('WebGL is unavailable');
    const gl=this.gl;
    const compile=(type,source)=>{
      const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);
      if (!gl.getShaderParameter(shader,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
      return shader;
    };
    const program=gl.createProgram();
    gl.attachShader(program,compile(gl.VERTEX_SHADER,vertexShader));
    gl.attachShader(program,compile(gl.FRAGMENT_SHADER,fragmentShader));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);this.program=program;
    const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
    const pos=gl.getAttribLocation(program,'a_position');gl.enableVertexAttribArray(pos);gl.vertexAttribPointer(pos,2,gl.FLOAT,false,0,0);
    this.uniforms={};
    for (const name of ['u_a','u_b','u_rectA','u_rectB','u_cropA','u_cropB','u_sceneA','u_sceneB','u_transition','u_edit','u_progress','u_resolution']) this.uniforms[name]=gl.getUniformLocation(program,name);
    gl.uniform1i(this.uniforms.u_a,0);gl.uniform1i(this.uniforms.u_b,1);
    this.textures=Array.from({length:6},()=>{
      const texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,1,1,0,gl.RGBA,gl.UNSIGNED_BYTE,new Uint8Array([0,0,0,255]));return texture;
    });
    this.uploaded=Array(6).fill(false);
    this.resize();
  }
  upload(i,source) {
    const gl=this.gl;
    gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,this.textures[i]);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,false);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,source);
    this.uploaded[i]=true;
  }
  resize() {
    const r=this.canvas.getBoundingClientRect();
    this.w=Math.max(1,r.width);this.h=Math.max(1,r.height);this.dpr=Math.max(window.devicePixelRatio||1,1);
    // Keep GPU output affordable without exceeding a 4K render surface.
    const renderDpr=Math.min(this.dpr,3840/this.w,3840/this.h,Math.sqrt(8294400/(this.w*this.h)));
    this.canvas.width=Math.round(this.w*renderDpr);this.canvas.height=Math.round(this.h*renderDpr);
    this.gl.viewport(0,0,this.canvas.width,this.canvas.height);
  }
  render(a,b,t,edit,progress) {
    const gl=this.gl,u=this.uniforms;
    gl.useProgram(this.program);
    gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,this.textures[a]);
    gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,this.textures[b]);
    gl.uniform4fv(u.u_rectA,rectFor(a,this.w,this.h,this.dpr));gl.uniform4fv(u.u_rectB,rectFor(b,this.w,this.h,this.dpr));
    gl.uniform4fv(u.u_cropA,crops[a]);gl.uniform4fv(u.u_cropB,crops[b]);
    gl.uniform1f(u.u_sceneA,a);gl.uniform1f(u.u_sceneB,b);gl.uniform1f(u.u_transition,t);gl.uniform1f(u.u_edit,edit);
    gl.uniform1f(u.u_progress,progress);gl.uniform2f(u.u_resolution,this.w,this.h);
    gl.drawArrays(gl.TRIANGLES,0,6);
  }
  destroy() { for(const texture of this.textures)this.gl.deleteTexture(texture);this.gl.deleteProgram(this.program); }
}
