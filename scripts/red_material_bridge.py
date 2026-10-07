"""Ruby-fold transport → red painted material → approved garment framing.

Only red material samples meet inside the flow-registered texture bridge. There
are no reveal masks, portals, wipes, whole-shot opacity layers or generated art.
"""
import cv2
import numpy as np


def smooth(t):
    t = np.clip(t, 0, 1)
    return t*t*(3-2*t)


class RedMaterialBridge:
    def __init__(self, source, destination, ruby_native, garment_native, garment_matrix):
        self.source = source.astype(np.float32)
        self.destination = destination.astype(np.float32)
        self.ruby_native = ruby_native
        self.garment_native = garment_native
        self.height, self.width = source.shape[:2]
        y, x = np.mgrid[:self.height, :self.width].astype(np.float32)
        self.x, self.y = x, y
        # Actual red-fold interior, excluding the pendant's white frame.
        self.ruby_x = 369+x/self.width*250
        self.ruby_y = 1120+y/self.height*335
        # Native-resolution garment detail: 1920 × 1080 original PNG pixels.
        self.garment_x = 1150+x
        self.garment_y = 3050+y
        inverse = cv2.invertAffineTransform(garment_matrix)
        self.end_x = inverse[0, 0]*x+inverse[0, 1]*y+inverse[0, 2]
        self.end_y = inverse[1, 0]*x+inverse[1, 1]*y+inverse[1, 2]
        self.ruby_field = self.sample_ruby(self.ruby_x, self.ruby_y)
        self.garment_field = self.sample_garment(self.garment_x, self.garment_y)
        # Flow analysis of real glass folds and paint strokes, not generation.
        small_a = cv2.resize(self.ruby_field.astype('uint8'), (480, 270))
        small_b = cv2.resize(self.garment_field.astype('uint8'), (480, 270))
        a = cv2.cvtColor(small_a, cv2.COLOR_RGB2GRAY)
        b = cv2.cvtColor(small_b, cv2.COLOR_RGB2GRAY)
        solver = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        forward = solver.calc(a, b, None)
        backward = solver.calc(b, a, None)
        self.forward = cv2.GaussianBlur(np.clip(cv2.resize(forward, (self.width, self.height))*4, -96, 96), (0, 0), 8)
        self.backward = cv2.GaussianBlur(np.clip(cv2.resize(backward, (self.width, self.height))*4, -96, 96), (0, 0), 8)

    def sample_ruby(self, x, y):
        return cv2.remap(self.ruby_native.astype(np.float32), x.astype(np.float32), y.astype(np.float32),
                         cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)

    def sample_garment(self, x, y):
        rgba = cv2.remap(self.garment_native, x.astype(np.float32), y.astype(np.float32),
                          cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=(244, 233, 225, 0))
        alpha = np.clip(rgba[..., 3:4].astype(np.float32)/255, 0, 1)
        return np.array([244, 233, 225], np.float32)*(1-alpha)+rgba[..., :3].astype(np.float32)*alpha

    def ruby_transport(self, progress):
        t = float(smooth(progress))
        # Nonlinear refractive transport follows the ruby's existing red folds.
        # No motion is added to the Ophelia source before this brief effect.
        material_x = 717+self.ruby_x*.45
        material_y = 108+self.ruby_y*.45
        distance = ((self.x-943)/300)**2+((self.y-692)/260)**2
        refraction = t/np.maximum(t+(1-t)*(.2+distance*.65), .00001)
        x = self.x*(1-refraction)+material_x*refraction
        y = self.y*(1-refraction)+material_y*refraction
        x += np.sin(np.pi*t)*np.sin((self.y-692)/150)*18
        y += np.sin(np.pi*t)*np.sin((self.x-943)/190)*6
        canvas = cv2.remap(self.source, x, y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
        # Native ruby samples avoid magnifying a previously downsampled frame.
        nx, ny = (x-717)/.45, (y-108)/.45
        native = self.sample_ruby(nx, ny)
        alpha = smooth(nx/71)*smooth((1078-nx)/71)*smooth(ny/67)*smooth((1918-ny)/76)
        alpha *= (nx>=0)&(nx<=1079)&(ny>=0)&(ny<=1919)
        return canvas+(native-canvas)*alpha[..., None]

    def material_morph(self, progress):
        t = float(smooth(progress))
        a = cv2.remap(self.ruby_field, self.x-self.forward[..., 0]*t,
                      self.y-self.forward[..., 1]*t, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        b = cv2.remap(self.garment_field, self.x-self.backward[..., 0]*(1-t),
                      self.y-self.backward[..., 1]*(1-t), cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        # Only the flow-registered red materials change representation here;
        # no portrait or complete clock is sitting behind a transparent pendant.
        base_a = cv2.GaussianBlur(a, (0, 0), 5)
        base_b = cv2.GaussianBlur(b, (0, 0), 5)
        material = base_a+(base_b-base_a)*t
        source_detail = (a-base_a)*(1-t)
        target_detail = (b-base_b)*t
        owns_source = np.linalg.norm(source_detail, axis=2)>np.linalg.norm(target_detail, axis=2)
        material += np.where(owns_source[..., None], source_detail, target_detail)
        return material

    def frame(self, progress):
        if progress <= 0:
            return self.source.copy()
        if progress >= 1:
            return self.destination.copy()
        if progress < .30:
            return self.ruby_transport(progress/.30)
        if progress < .64:
            return self.material_morph((progress-.30)/.34)
        t = float(smooth((progress-.64)/.36))
        # Resolve the transported paint into the exact approved starting frame.
        x = self.garment_x*(1-t)+self.end_x*t
        y = self.garment_y*(1-t)+self.end_y*t
        return self.sample_garment(x, y)
