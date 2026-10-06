export const vertexShader = `
attribute vec2 a_position;
varying vec2 v_uv;
void main() {
  v_uv = vec2(a_position.x * .5 + .5, .5 - a_position.y * .5);
  gl_Position = vec4(a_position, 0., 1.);
}`;

export const fragmentShader = `
precision highp float;
varying vec2 v_uv;
uniform sampler2D u_a;
uniform sampler2D u_b;
uniform vec4 u_rectA;
uniform vec4 u_rectB;
uniform vec4 u_cropA;
uniform vec4 u_cropB;
uniform float u_sceneA;
uniform float u_sceneB;
uniform float u_transition;
uniform float u_edit;
uniform float u_progress;
uniform vec2 u_resolution;

float luminance(vec3 c) { return dot(c, vec3(.2126, .7152, .0722)); }
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p); f = f*f*(3.-2.*f);
  return mix(mix(hash(i), hash(i+vec2(1.,0.)), f.x), mix(hash(i+vec2(0.,1.)), hash(i+vec2(1.)), f.x), f.y);
}
float weave(vec2 p) { return .62*noise(p*3.1) + .25*noise(p*7.3) + .13*noise(p*15.); }
vec3 background(float scene, vec4 rect) {
  if (scene < .5) return vec3(0.);
  if (scene < 1.5) {
    float atmosphere = exp(-length((v_uv-vec2(.38,.43))*vec2(1.,.8))*3.);
    return mix(vec3(.018,.033,.049), vec3(.031,.075,.105), atmosphere);
  }
  if (scene < 2.5) return vec3(243.,233.,221.)/255.;
  if (scene < 3.5) {
    vec2 centre = rect.xy + rect.zw*.5;
    // An open vertical atmosphere has no rectangular top/bottom boundary.
    float horizontal = (v_uv.x-centre.x)/(rect.z*.80);
    float vertical = (v_uv.y-centre.y)/rect.w;
    float ambient = exp(-pow(abs(horizontal),6.))*(.985+.012*exp(-vertical*vertical));
    return mix(vec3(244.,233.,225.)/255., vec3(.0196,.0118,.0078), ambient);
  }
  if (scene < 4.5) return vec3(244.,233.,225.)/255.;
  return vec3(.022,.037,.047);
}
vec4 foreground(sampler2D tex, vec4 rect, vec4 crop, float scene) {
  vec2 local = (v_uv-rect.xy)/rect.zw;
  vec2 sourceUV = crop.xy + local*crop.zw;
  vec4 c = texture2D(tex, clamp(sourceUV, .001, .999));
  float inside = step(0.,local.x)*step(local.x,1.)*step(0.,local.y)*step(local.y,1.);
  float edge = 1.;
  if (scene > .5 && scene < 1.5 || scene > 4.5) {
    // Blend only peripheral environment pixels into the separate surround.
    edge = smoothstep(0.,.055,local.x)*smoothstep(0.,.055,1.-local.x)
         * smoothstep(0.,.045,local.y)*smoothstep(0.,.06,1.-local.y);
  }
  if (scene > 2.5 && scene < 3.5) {
    edge = smoothstep(0.,.075,local.x)*smoothstep(0.,.075,1.-local.x)
         * smoothstep(0.,.035,local.y)*smoothstep(0.,.095,1.-local.y);
  }
  if (scene > 3.5 && scene < 4.5) {
    // Matte the real oval clock, not its rectangular cream video canvas.
    // The interior is protected, including pale lettering and painted detail.
    vec2 ellipse = (sourceUV-vec2(.503,.496))/vec2(.265,.493);
    float r = length(ellipse);
    vec3 cream = vec3(244.,233.,216.)/255.;
    float exteriorKey = smoothstep(.025,.105,length(c.rgb-cream));
    float protectedInterior = 1.-smoothstep(.89,.975,r);
    edge = max(exteriorKey,protectedInterior)*(1.-smoothstep(1.005,1.035,r));
  }
  c.a *= inside*edge;
  return c;
}
vec3 composite(vec3 bg, vec4 fg) { return mix(bg, fg.rgb, fg.a); }
float reveal(float score, float p, float feather) {
  float threshold = mix(1.12,-.12,p);
  return smoothstep(threshold-feather,threshold+feather,score);
}
float softLight(sampler2D tex, vec4 rect, vec4 crop) {
  // Blur the control signal, never the artwork. Broad luminance neighborhoods
  // prevent a reveal from cutting individual eyes, skin, or painted strokes.
  vec2 uv = crop.xy + ((v_uv-rect.xy)/rect.zw)*crop.zw;
  vec2 d = crop.zw*vec2(.075,.065);
  vec3 c = texture2D(tex,clamp(uv,.001,.999)).rgb*.20;
  c += texture2D(tex,clamp(uv+vec2(d.x,0.),.001,.999)).rgb*.12;
  c += texture2D(tex,clamp(uv-vec2(d.x,0.),.001,.999)).rgb*.12;
  c += texture2D(tex,clamp(uv+vec2(0.,d.y),.001,.999)).rgb*.12;
  c += texture2D(tex,clamp(uv-vec2(0.,d.y),.001,.999)).rgb*.12;
  c += texture2D(tex,clamp(uv+d,.001,.999)).rgb*.08;
  c += texture2D(tex,clamp(uv-d,.001,.999)).rgb*.08;
  c += texture2D(tex,clamp(uv+vec2(d.x,-d.y),.001,.999)).rgb*.08;
  c += texture2D(tex,clamp(uv+vec2(-d.x,d.y),.001,.999)).rgb*.08;
  return luminance(c);
}
void main() {
  vec4 fa = foreground(u_a,u_rectA,u_cropA,u_sceneA);
  vec4 fb = foreground(u_b,u_rectB,u_cropB,u_sceneB);
  vec3 ba = background(u_sceneA,u_rectA), bb = background(u_sceneB,u_rectB);
  vec3 a = composite(ba,fa), b = composite(bb,fb);
  float p = clamp(u_transition,0.,1.);
  if (u_edit < -.5 || p < .0001) { gl_FragColor=vec4(a,1.); return; }
  if (p > .9999) { gl_FragColor=vec4(b,1.); return; }
  float n = weave(v_uv*vec2(u_resolution.x/u_resolution.y,1.));
  float la = softLight(u_a,u_rectA,u_cropA), lb = softLight(u_b,u_rectB,u_cropB);
  vec3 result = a;
  if (u_edit < -.5 || p < .0001) result = a;
  else if (p > .9999) result = b;
  else if (u_edit < .5) {
    // Stone light becomes plant light: incoming forest detail participates
    // throughout the overlap; there is no fade-to-black interstitial.
    float plant = exp(-dot((v_uv-vec2(.23,.69))*vec2(1.9,1.4),(v_uv-vec2(.23,.69))*vec2(1.9,1.4)));
    float score = .23*clamp(lb*2.2,0.,1.) + .25*n + .52*plant;
    float forest = reveal(score,min(1.,p*1.12),.17);
    float pendant = 1.-reveal(.62*n+.38*plant,min(1.,p*1.9),.18);
    result = mix(composite(ba,vec4(fa.rgb,fa.a*pendant)),b,forest);
  } else if (u_edit < 1.5) {
    // The physical object arrives ahead of its pale environment; the forest
    // leaves through a graded, textured field rather than a rectangular cut.
    float score = .68*v_uv.x + .24*n + .08*clamp(la*1.8,0.,1.);
    float world = reveal(score,min(1.,p*1.55),.22);
    vec3 ground = mix(a,bb,world);
    float material = reveal(.40*n+.25*clamp(lb*1.7,0.,1.)+.35*(1.-v_uv.y), min(1.,p*1.55),.20);
    result = mix(ground,fb.rgb,fb.a*material);
  } else if (u_edit < 2.5) {
    // A sharp portrait inhabits its own dark surround. Material light recedes
    // before the face becomes dominant, avoiding a double-subject exposure.
    vec2 c = u_rectB.xy+u_rectB.zw*.5;
    float vicinity = exp(-dot((v_uv-c)*vec2(1.5,.8),(v_uv-c)*vec2(1.5,.8))*2.);
    float score = .55*vicinity+.30*n+.15*clamp(lb*1.8,0.,1.);
    float world = reveal(score,min(1.,p*1.3),.20);
    float material = 1.-reveal(.60*n+.40*vicinity,min(1.,p*1.75),.18);
    vec3 ground = mix(composite(ba,vec4(fa.rgb,fa.a*material)),bb,world);
    float portrait = reveal(.65*vicinity+.25*n+.10*clamp(lb*1.6,0.,1.), min(1.,p*1.20),.20);
    result = mix(ground,fb.rgb,fb.a*portrait);
  } else if (u_edit < 3.5) {
    // Ivory, red paint, and the oval artifact guide a selective substitution.
    // The protected clock matte never carries the source video's cream box.
    float score = .25*clamp(lb*1.4,0.,1.)+.40*n+.35*(1.-v_uv.y);
    float world = reveal(.55*n+.45*v_uv.x,min(1.,p*1.7),.23);
    float portrait = 1.-reveal(.65*n+.35*v_uv.x,min(1.,p*1.8),.19);
    vec3 ground = mix(composite(ba,vec4(fa.rgb,fa.a*portrait)),bb,world);
    float artwork = reveal(score,min(1.,p*1.40),.20);
    result = mix(ground,fb.rgb,fb.a*artwork);
  } else {
    // Gaze-led connection: owl eyes and feather detail lead the forest;
    // the clock background cannot float over the next shot because it is matted.
    float gaze = exp(-dot((v_uv-vec2(.53,.32))*vec2(1.8,2.2),(v_uv-vec2(.53,.32))*vec2(1.8,2.2))*2.);
    float score = .55*gaze+.30*n+.15*clamp(lb*2.,0.,1.);
    float clock = 1.-reveal(.55*gaze+.45*n,min(1.,p*1.8),.19);
    result = mix(composite(ba,vec4(fa.rgb,fa.a*clock)),b,reveal(score,min(1.,p*1.12),.19));
  }
  gl_FragColor = vec4(result,1.);
}`;
