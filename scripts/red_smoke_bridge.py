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
    # Retime the established field, rather than append a hold or another effect.
    # The red source, peak cover and gradual garment formation now have distinct,
    # overlapping reading time. C1 monotone interpolation keeps the plume moving.
    EVENT_SECONDS = np.array([0, .36, .85, 1.10, 1.28, 1.65, 2.10, 2.70, 3.25, 3.95, 4.56, 4.80])
    EVENT_PHASES = np.array([0, .055, .116, .148, .23, .26, .285, .32, .41, .62, .95, 1])

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
        intervals = np.diff(self.EVENT_SECONDS)
        slopes = np.diff(self.EVENT_PHASES)/intervals
        self.timing_slopes = np.r_[slopes[0], np.zeros(len(slopes)-1), slopes[-1]]
        for i in range(1, len(slopes)):
            w1, w2 = 2*intervals[i]+intervals[i-1], intervals[i]+2*intervals[i-1]
            self.timing_slopes[i] = (w1+w2)/(w1/slopes[i-1]+w2/slopes[i])
        for i in range(19):
            theta = i*2.399963 + rng.uniform(-.22, .22)
            self.lobes.append((theta, rng.uniform(.35, 1), rng.uniform(.7, 1.25),
                               rng.uniform(.7, 1.1), rng.uniform(-1, 1)))

    def event_progress(self, progress):
        seconds = float(np.clip(progress, 0, 1))*self.EVENT_SECONDS[-1]
        i = min(np.searchsorted(self.EVENT_SECONDS, seconds, side='right')-1,
                len(self.EVENT_SECONDS)-2)
        duration = self.EVENT_SECONDS[i+1]-self.EVENT_SECONDS[i]
        t = (seconds-self.EVENT_SECONDS[i])/duration
        a, b = self.EVENT_PHASES[i:i+2]
        da, db = self.timing_slopes[i:i+2]
        return float((2*t**3-3*t*t+1)*a+(t**3-2*t*t+t)*duration*da
                     +(-2*t**3+3*t*t)*b+(t**3-t*t)*duration*db)

    def layer(self, progress, artwork_alpha=None):
        p = self.event_progress(progress)
        # The original short emission opens into a field that keeps evolving
        # throughout the camera move, rather than extinguishing before it.
        expansion = float(smooth(min(p/.22, 1)))
        # Drift is continuous in real time even while the density/reveal
        # envelope spends longer in its formative middle portion.
        phase = float(progress)*2.58
        radius = 5+390*expansion**1.45
        ox, oy = self.origin
        nx = self.x+17*np.sin(self.y/49+phase*2.0)+45*phase
        ny = self.y+13*np.sin(self.x/61-phase*1.5)+60*phase
        noise = np.zeros((self.h, self.w), np.float32)
        for i, field in enumerate(self.fields):
            noise += cv2.remap(field, nx*(1+i*.035), ny*(1+i*.04),
                               cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)/(2**i)
        noise /= 1.75
        # Curl the atmosphere itself. These coordinates never sample media.
        qx = self.x+(noise-.5)*70*expansion+np.sin(self.y/24+phase*3)*10*expansion
        qy = self.y+np.sin(self.x/33-phase*2)*12*expansion
        density = np.zeros((self.h, self.w), np.float32)
        # A cluster of differently sized curls grows out of the stone, expands
        # toward the lens and drifts upwards. No expanding geometric scene mask.
        for theta, distance, size, weight, curl in self.lobes:
            travel = radius*distance*.43
            angle = theta+curl*phase*.28
            cx = ox+np.cos(angle)*travel
            cy = oy+np.sin(angle)*travel*.70-40*phase
            sx = radius*size*.48
            sy = sx*(.73+.16*np.sin(theta+phase))
            density += weight*np.exp(-.5*((qx-cx)/sx)**2-.5*((qy-cy)/sy)**2)
        density *= .25+noise*1.7
        density *= float(smooth(p/.047))*.70
        if p > .16:
            # The rising cloud carries the opening toward the red bodice,
            # rather than resolving the clock's lower lettering first.
            opening_y = oy-30*float(smooth((p-.16)/.20))
            distance = np.sqrt(((qx-ox)/250)**2+((qy-opening_y)/210)**2)
            dispersal = float(smooth((p-.16)/.74))
            # Break apart dense curls instead of uniformly fading an overlay.
            clearing = .35+2.8*np.exp(-distance**2/.65)+noise*.2
            # Erode each moving curl relative to its own density. The old
            # fixed subtraction extinguished the whole field in a few frames.
            density *= np.maximum(0, 1-dispersal*clearing)
            # The emission zone opens first into the painted red anchor, while
            # other curls keep moving and resolving through the wider pullback.
            early = float(smooth((p-.16)/.23))
            density *= np.maximum(0, 1-early*1.8*np.exp(-distance**2/.65))
        # Lower optical thickness during dispersal: curls become translucent
        # before breaking apart, instead of clearing in a few abrupt frames.
        thickness = 1.0-float(smooth((p-.16)/.18))*.82
        opacity = 1-np.exp(-density*thickness)
        # A few completely occluded frames conceal the change of intact shots.
        # Texture/light stays continuous through that opaque part of the cloud.
        occlusion = float(smooth((p-.116)/.0175)*(1-smooth((p-.157)/.025)))
        opacity += occlusion*(1-opacity)
        lingering_density = opacity.copy()
        if p > .62:
            # Dissipation starts in the emission/red-garment zone, with organic
            # density variations; the cloud's fringes drift away last.
            opacity *= float(smooth((.95-p)/.33))
        if artwork_alpha is not None:
            # The same dispersing field retreats onto the revealed ivory,
            # while the artwork resolves cleanly. Preserve the early handoff.
            seconds = float(progress)*self.EVENT_SECONDS[-1]
            retreat = float(smooth((seconds-2.70)/.60))
            silhouette = cv2.resize(artwork_alpha[..., 0], (self.w, self.h),
                                    interpolation=cv2.INTER_AREA)
            peripheral_falloff = float(1-smooth((seconds-3.65)/.95))
            # Keep the existing advected curls readable as separated wisps,
            # rather than a uniform pink tint on the ivory surround.
            filaments = smooth((noise-.39)/.22)
            wisps = (1-np.exp(-lingering_density*3.0))*filaments*peripheral_falloff
            opacity = opacity*(1-retreat)+wisps*retreat*(1-silhouette)
            # Absolute preview deadline: 1.4s source lead + 4.6s field = 6s.
            if seconds >= 4.60:
                opacity.fill(0)
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
        self.clarity += (visibility-self.clarity)*.075
        # Finish the optical recovery continuously while the camera keeps moving.
        completion = float(smooth((progress-.84)/.12))
        clarity = self.clarity+(1-self.clarity)*completion
        broad_weight = visibility
        paint_weight = visibility*clarity
        fine_weight = visibility*clarity**4
        low = self.soft_frame(incoming, 88, 8)
        medium = self.soft_frame(incoming, 22, 4)
        soft = self.soft_frame(incoming, 4, 2)
        # Convex combinations preserve source colors. Recover local contrast
        # and sharpness via spatial-frequency detail, with no color grading.
        formed = low*(1-broad_weight)+medium*(broad_weight-paint_weight)
        formed += soft*(paint_weight-fine_weight)+incoming*fine_weight
        return formed, visibility, low

    def frame(self, progress, outgoing, incoming, artwork_alpha=None):
        if progress <= 0:
            return outgoing.copy()
        if progress >= 1:
            return incoming.copy()
        opacity, smoke = self.layer(progress, artwork_alpha)
        event = self.event_progress(progress)
        # Ophelia loses visibility inside the cloud. Shila starts with no clean
        # detail at all, then is constructed from the same local density field.
        exit_strength = float(1-smooth((event-.116)/.032))
        outgoing_weight = (1-opacity)*exit_strength
        if event <= .148:
            return outgoing*outgoing_weight+smoke*(1-outgoing_weight)
        formed, incoming_weight, broad_color = self.formation(incoming, opacity, event)
        # Real garment light/color diffuses into the cloud itself; recognizable
        # painted detail then resolves locally from that same medium.
        color_transfer = incoming_weight**.7*.50
        medium = smoke*(1-color_transfer)+broad_color*color_transfer
        return formed*incoming_weight+medium*(1-incoming_weight)
