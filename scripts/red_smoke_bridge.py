"""Smoke-density-driven formation of a moving, undistorted Shila artwork.

The smoke field controls visibility and the recovery of broad contrast, painted
texture and fine detail independently. There is no clean incoming shot beneath
a foreground smoke overlay. Source pixel coordinates are never displaced.
"""
import cv2
import numpy as np


def smooth(t):
    t = np.clip(t, 0, 1)
    return t*t*(3-2*t)


class RedSmokeBridge:
    def __init__(self, width=1920, height=1080, origin=(947, 760)):
        self.width, self.height = width, height
        self.origin = np.asarray(origin, np.float32)/4
        self.h, self.w = height//4, width//4
        self.y, self.x = np.mgrid[:self.h, :self.w].astype(np.float32)
        rng = np.random.default_rng(7013)
        # Coherent low-frequency density, advected continuously through the
        # plume. These fields affect smoke only, never either artwork.
        self.fields = []
        for size, sigma in [(8, 3), (17, 2), (37, 1.5)]:
            values = rng.random((size, size*2), dtype=np.float32)
            values = cv2.resize(values, (self.w*2, self.h*2), interpolation=cv2.INTER_CUBIC)
            self.fields.append(cv2.GaussianBlur(values, (0, 0), sigma))
        self.lobes = []
        self.clarity = np.zeros((height, width, 1), np.float32)
        for i in range(19):
            theta = i*2.399963 + rng.uniform(-.22, .22)
            self.lobes.append((theta, rng.uniform(.35, 1), rng.uniform(.7, 1.25),
                               rng.uniform(.7, 1.1), rng.uniform(-1, 1)))

    def layer(self, progress):
        p = float(np.clip(progress, 0, 1))
        expansion = float(smooth(min(p/.56, 1)))
        radius = 5+390*expansion**1.45
        ox, oy = self.origin
        nx = self.x+17*np.sin(self.y/49+p*2.0)+45*p
        ny = self.y+13*np.sin(self.x/61-p*1.5)+60*p
        noise = np.zeros((self.h, self.w), np.float32)
        for i, field in enumerate(self.fields):
            noise += cv2.remap(field, nx*(1+i*.035), ny*(1+i*.04),
                               cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)/(2**i)
        noise /= 1.75
        # Curl the atmosphere itself. These coordinates never sample media.
        qx = self.x+(noise-.5)*70*expansion+np.sin(self.y/24+p*3)*10*expansion
        qy = self.y+np.sin(self.x/33-p*2)*12*expansion
        density = np.zeros((self.h, self.w), np.float32)
        # A cluster of differently sized curls grows out of the stone, expands
        # toward the lens and drifts upwards. No expanding geometric scene mask.
        for theta, distance, size, weight, curl in self.lobes:
            travel = radius*distance*.43
            angle = theta+curl*p*.28
            cx = ox+np.cos(angle)*travel
            cy = oy+np.sin(angle)*travel*.70-40*p*p
            sx = radius*size*.48
            sy = sx*(.73+.16*np.sin(theta+p))
            density += weight*np.exp(-.5*((qx-cx)/sx)**2-.5*((qy-cy)/sy)**2)
        density *= .25+noise*1.7
        density *= float(smooth(p/.12))*1.7
        if p > .405:
            distance = np.sqrt(((qx-ox)/250)**2+((qy-oy)/210)**2)
            dispersal = float(smooth((p-.405)/.48))
            # Break apart dense curls instead of uniformly fading an overlay.
            clearing = .35+2.8*np.exp(-distance**2/.65)+noise*.2
            density = np.maximum(0, density-dispersal*38*clearing)
        # Lower optical thickness during dispersal: curls become translucent
        # before breaking apart, instead of clearing in a few abrupt frames.
        thickness = 1.0-float(smooth((p-.405)/.12))*.65
        opacity = 1-np.exp(-density*thickness)
        # A few completely occluded frames conceal the change of intact shots.
        # Texture/light stays continuous through that opaque part of the cloud.
        occlusion = float(smooth((p-.30)/.045)*(1-smooth((p-.405)/.055)))
        opacity += occlusion*(1-opacity)
        if p > .66:
            # Dissipation starts in the emission/red-garment zone, with organic
            # density variations; the cloud's fringes drift away last.
            opacity *= float(smooth((.80-p)/.14))
        # Backlit volume shading, sampled from a restrained ruby-red palette.
        # Added atmosphere is independent; source colors are not graded.
        shade = np.clip((noise-.24)*1.9, 0, 1)
        lighting = np.clip(.20+shade*.75+np.exp(-((self.x-ox)/170)**2-
                                             ((self.y-oy+30)/130)**2)*.08, 0, 1)
        dark = np.array([67, 10, 23], np.float32)
        light = np.array([161, 43, 52], np.float32)
        color = dark+(light-dark)*lighting[..., None]
        opacity = cv2.GaussianBlur(opacity, (0, 0), 3.3)
        opacity = cv2.resize(opacity, (self.width, self.height), interpolation=cv2.INTER_CUBIC)
        color = cv2.resize(color, (self.width, self.height), interpolation=cv2.INTER_CUBIC)
        return np.clip(opacity, 0, 1)[..., None], color

    @staticmethod
    def soft_frame(frame, sigma, divisor):
        height, width = frame.shape[:2]
        small = cv2.resize(frame, (width//divisor, height//divisor), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), sigma/divisor)
        return cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)

    def formation(self, incoming, opacity, progress):
        # Density itself is the spatial transition matte. Different patches
        # resolve as their local cloud thins, never from a global shot opacity.
        visibility = smooth(1-opacity)
        self.clarity += (visibility-self.clarity)*.24
        # Finish the optical recovery continuously while the camera keeps moving.
        completion = float(smooth((progress-.70)/.16))
        clarity = self.clarity+(1-self.clarity)*completion
        broad_weight = visibility
        paint_weight = visibility*clarity
        fine_weight = visibility*clarity**3
        low = self.soft_frame(incoming, 88, 8)
        medium = self.soft_frame(incoming, 22, 4)
        soft = self.soft_frame(incoming, 4, 2)
        # Convex combinations preserve source colors. Recover local contrast
        # and sharpness via spatial-frequency detail, with no color grading.
        formed = low*(1-broad_weight)+medium*(broad_weight-paint_weight)
        formed += soft*(paint_weight-fine_weight)+incoming*fine_weight
        return formed, visibility

    def frame(self, progress, outgoing, incoming):
        if progress <= 0:
            return outgoing.copy()
        if progress >= 1:
            return incoming.copy()
        opacity, smoke = self.layer(progress)
        # Ophelia loses visibility inside the cloud. Shila starts with no clean
        # detail at all, then is constructed from the same local density field.
        exit_strength = float(1-smooth((progress-.30)/.08))
        outgoing_weight = (1-opacity)*exit_strength
        if progress <= .38:
            return outgoing*outgoing_weight+smoke*(1-outgoing_weight)
        formed, incoming_weight = self.formation(incoming, opacity, progress)
        return formed*incoming_weight+smoke*(1-incoming_weight)
