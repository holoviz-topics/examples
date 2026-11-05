"""
Module that supports the grabcut.ipynb example.

Its content has been extracted and adapted from earthsim.holoviz.org.
"""

import math

import param
import panel as pn
import numpy as np
import holoviews as hv
import geoviews as gv
import cartopy.crs as ccrs
import datashader as ds

from PIL import Image, ImageDraw
from geoviews.util import path_to_geom_dicts
from holoviews.core.operation import Operation
from holoviews.core.options import Store, Options
from holoviews.core.spaces import DynamicMap
from holoviews.core.util import pd
from holoviews.element.util import split_path
from holoviews.operation.datashader import ResampleOperation2D, rasterize, regrid
from holoviews.operation import contours
from holoviews.streams import FreehandDraw, BoxEdit
from shapely.geometry import Polygon, LinearRing, MultiPolygon


def paths_to_polys(path):
    """
    Converts a Path object to a Polygons object by extracting all paths
    interpreting inclusion zones as holes and then constructing Polygon
    and MultiPolygon geometries for each path.
    """
    geoms = path_to_geom_dicts(path)

    polys = []
    for geom in geoms:
        g = geom['geometry']
        found = False
        for p in list(polys):
            if Polygon(p['geometry']).contains(g):
                if 'holes' not in p:
                    p['holes'] = []
                p['holes'].append(g)
                found = True
            elif Polygon(g).contains(p['geometry']):
                polys.pop(polys.index(p))
                if 'holes' not in geom:
                    geom['holes'] = []
                geom['holes'].append(p['geometry'])
        if not found:
            polys.append(geom)

    polys_with_holes = []
    for p in polys:
        geom = p['geometry']
        holes = []
        if 'holes' in p:
            holes = [LinearRing(h) for h in p['holes']]

        if 'Multi' in geom.geom_type:
            polys = []
            for g in geom:
                subholes = [h for h in holes if g.intersects(h)]
                polys.append(Polygon(g, subholes))
            poly = MultiPolygon(polys)
        else:
            poly = Polygon(geom, holes)
        p['geometry'] = poly
        polys_with_holes.append(p)
    return path.clone(polys_with_holes, new_type=gv.Polygons)


class rasterize_polygon(ResampleOperation2D):
    """
    Rasterizes Polygons elements to a boolean mask using PIL
    """

    def _process(self, element, key=None):
        sampling = self._get_sampling(element, 0, 1)
        (x_range, y_range), (xvals, yvals), (width, height), (xtype, ytype) = sampling
        (x0, x1), (y0, y1) = x_range, y_range
        img = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(img)
        for poly in element.split():
            poly = poly.reindex(vdims=[])
            for p in split_path(poly):
                xs, ys = (p.values if pd else p).T
                xs = ((xs - x0) / (x1-x0) * width)
                ys = ((ys - y0) / (y1-y0) * height)
                draw.polygon(list(zip(xs, ys)), outline=1, fill=1)
        img = np.array(img).astype('bool')
        return hv.Image((xvals, yvals, img), element.kdims)


class extract_foreground(Operation):
    """
    Uses Grabcut algorithm to extract the foreground from an image given
    path or polygon types.
    """

    foreground = param.ClassSelector(class_=hv.Path)

    background = param.ClassSelector(class_=hv.Path)

    iterations = param.Integer(default=5, bounds=(0, 20), doc="""
        Number of iterations to run the GrabCut algorithm for.""")


    def _process(self, element, key=None):
        try:
            import cv2 as cv
        except:
            # HACK: Avoids error loading OpenCV the first time
            # ImportError dlopen: cannot load any more object with static TLS
            try:
                import cv2 as cv
            except ImportError:
                raise ImportError('GrabCut algorithm requires openCV')

        if isinstance(self.p.foreground, hv.Polygons):
            rasterize_op = rasterize_polygon
        else:
            rasterize_op = rasterize.instance(aggregator=ds.any())

        kwargs = {'dynamic': False, 'target': element}
        fg_mask = rasterize_op(self.p.foreground, **kwargs)
        bg_mask = rasterize_op(self.p.background, **kwargs)
        fg_mask = fg_mask.dimension_values(2, flat=False)
        bg_mask = bg_mask.dimension_values(2, flat=False)

        # UPDATE wrt earthsim: Newer versions of holoviews return np.nan instead of 0 (I think)
        fg_mask = np.nan_to_num(fg_mask)
        bg_mask = np.nan_to_num(bg_mask)

        if fg_mask[np.isfinite(fg_mask)].sum() == 0 or bg_mask[np.isfinite(bg_mask)].sum() == 0:
            return element.clone([], vdims=['Foreground'], new_type=gv.Image,
                                 crs=element.crs)

        mask = np.where(fg_mask, 1, 2)
        mask = np.where(bg_mask, 0, mask).copy()
        bgdModel = np.zeros((1,65), np.float64)
        fgdModel = np.zeros((1,65), np.float64)

        if isinstance(element, hv.RGB):
            img = np.dstack([element.dimension_values(d, flat=False)
                             for d in element.vdims])
        else:
            img = element.dimension_values(2, flat=False)
        mask, _, _ = cv.grabCut(img, mask.astype('uint8'), None, bgdModel, fgdModel,
                                self.p.iterations, cv.GC_INIT_WITH_MASK)
        fg_mask = np.where((mask==2)|(mask==0),0,1).astype('bool')
        xs, ys = (element.dimension_values(d, expanded=False) for d in element.kdims)
        return element.clone((xs, ys, fg_mask), vdims=['Foreground'], new_type=gv.Image,
                             crs=element.crs)

class filter_polygons(Operation):

    minimum_size = param.Integer(default=10)

    link_inputs = param.Boolean(default=True)

    def _process(self, element, key=None):
        paths = []
        for path in element.split():
            # UPDATE wrt earthsim: len(path) returns 1 I guess because it's a multipath and that is has only one path
            # UPDATE wrt earthsim: Is there a better way to get the number of vertices in a path?
            # if len(path) < self.p.minimum_size:
            if len(path.dimension_values('Longitude')) < self.p.minimum_size:
                continue
            for p in split_path(path):
                if len(p) > self.p.minimum_size:
                    paths.append(p)
        return element.clone(paths)


class simplify_paths(Operation):

    tolerance = param.Number(default=0.01)

    def _process(self, element, key=None):
        paths = []
        for g in path_to_geom_dicts(element):
            geom = g['geometry']
            g = dict(g, geometry=geom.simplify(self.p.tolerance))
            paths.append(g)
        return element.clone(paths)


class GrabCutPanel(param.Parameterized):
    """
    Defines a Panel for extracting contours from an Image.
    """

    crs = param.ClassSelector(default=ccrs.PlateCarree(), class_=ccrs.Projection,
                              precedence=-1, doc="""
        Projection the inputs and output paths are defined in.""")

    image = param.ClassSelector(class_=gv.RGB, precedence=-1, doc="""
        The Image to compute contours on""")

    path_type = param.ClassSelector(default=gv.Path, class_=hv.Path,
                                    precedence=-1, is_instance=False, doc="""
        The element type to draw into.""")

    downsample = param.Magnitude(default=1, precedence=1, doc="""
        Amount to downsample image by before applying grabcut.""")

    iterations = param.Integer(default=5, precedence=1, bounds=(0, 20), doc="""
        Number of iterations to run the GrabCut algorithm for.""")

    clear = param.Action(default=lambda o: o._trigger_clear(),
                                  precedence=2, doc="""
        Button to clear drawn annotations.""")

    update_contour = param.Action(default=lambda o: o.param.trigger('update_contour'),
                                  precedence=2, doc="""
        Button triggering GrabCut.""")

    minimum_size = param.Integer(default=100, precedence=3)

    filter_contour = param.Action(default=lambda o: o.param.trigger('filter_contour'),
                                  precedence=4, doc="""
        Button triggering filtering of contours.""")

    tolerance = param.Number(default=0.01, precedence=5)

    simplify_contour = param.Action(default=lambda o: o.param.trigger('simplify_contour'),
                                    precedence=6, doc="""
        Simplifies contour.""" )

    width = param.Integer(default=500, precedence=-1, doc="""
        Width of the plot""")

    height = param.Integer(default=None, precedence=-1, doc="""
        Height of the plot""")

    def __init__(self, image, fg_data=[], bg_data=[], **params):
        super().__init__(image=image, **params)
        self._bg_data = bg_data
        self._fg_data = fg_data
        self.bg_paths = DynamicMap(self.bg_path_view)
        self.fg_paths = DynamicMap(self.fg_path_view)
        self.draw_bg = FreehandDraw(source=self.bg_paths, tooltip="draw_fg")
        self.draw_fg = FreehandDraw(source=self.fg_paths, tooltip="draw_bg")
        self._clear = False

    def _trigger_clear(self):
        self._clear = True
        self.param.trigger('clear')
        self._clear = False

    @param.depends('clear')
    def bg_path_view(self):
        if self._clear:
            self._bg_data = []
        elif self.bg_paths.data:
            self._bg_data = self.draw_bg.element.data
        else:
            self._bg_data = gv.project(self.path_type(self._bg_data, crs=self.crs), projection=self.image.crs)
        return self.path_type(self._bg_data, crs=self.image.crs).opts(color='cyan')

    @param.depends('clear')
    def fg_path_view(self):
        if self._clear:
            self._fg_data = []
        elif self.fg_paths.data:
            self._fg_data = self.draw_fg.element.data
        else:
            self._fg_data = gv.project(self.path_type(self._fg_data, crs=self.crs), projection=self.image.crs)
        return self.path_type(self._fg_data, crs=self.image.crs).opts(color='red')

    @param.depends('update_contour', 'image')
    def extract_foreground(self, **kwargs):
        img = self.image
        bg, fg = self.bg_path_view(), self.fg_path_view()

        if not len(bg) or not len(fg):
            return gv.Path([], img.kdims, crs=img.crs)

        if self.downsample != 1:
            kwargs = {'dynamic': False}
            h, w = img.interface.shape(img, gridded=True)
            kwargs['width'] = int(w*self.downsample)
            kwargs['height'] = int(h*self.downsample)
            img = regrid(img, **kwargs)

        foreground = extract_foreground(img, background=bg, foreground=fg,
                                        iterations=self.iterations)
        # UPDATE wrt earthsim: No need here to wrap the outpout of countours() in a list
        foreground = gv.Path(contours(foreground, filled=True, levels=1).split()[0].data,
                             kdims=foreground.kdims, crs=foreground.crs)
        self.result = gv.project(foreground, projection=self.crs)
        return foreground

    @param.depends('filter_contour')
    def _filter_contours(self, obj, **kwargs):
        if self.minimum_size > 0:
            obj = filter_polygons(obj, minimum_size=self.minimum_size)
        return obj

    @param.depends('simplify_contour')
    def _simplify_contours(self, obj, **kwargs):
        if self.tolerance > 0:
            obj = simplify_paths(obj, tolerance=self.tolerance)
        self.result = gv.project(obj, projection=self.crs)
        return obj

    def view(self):
        height = self.height
        if height is None:
            h, w = self.image.dimension_values(2, flat=False).shape[:2]
            height = int(self.width*(h/w))
        options = dict(width=self.width, height=height, xaxis=None, yaxis=None,
                       projection=self.image.crs)
        dmap = hv.DynamicMap(self.extract_foreground)
        dmap = hv.util.Dynamic(dmap, operation=self._filter_contours)
        dmap = hv.util.Dynamic(dmap, operation=self._simplify_contours)
        return (self.image.opts(**options) * self.bg_paths * self.fg_paths +
                dmap.opts(**options)).opts(toolbar="left")

    @param.output(polys=hv.Path)
    def output(self):
        return self.result

    def panel(self):
        return pn.Row(self.param, self.view())


class SelectRegionPanel(param.Parameterized):
    """
    Visualization that allows selecting a bounding box anywhere on a tile source.
    """

    # Tile servers
    misc_servers = {'OpenStreetMap': 'http://c.tile.openstreetmap.org/{Z}/{X}/{Y}.png',
                    'Basemaps CartoCDN': 'https://s.basemaps.cartocdn.com/light_all/{Z}/{X}/{Y}.png',
                    'Stamen': 'http://tile.stamen.com/terrain/{Z}/{X}/{Y}.png'}

    arcgis_paths = {'World Imagery': 'World_Imagery/MapServer/tile/{Z}/{Y}/{X}',
                    'World Topo Map': 'World_Topo_Map/MapServer/tile/{Z}/{Y}/{X}',
                    'World Terrain Base': 'World_Terrain_Base/MapServer/tile/{Z}/{Y}/{X}',
                    'World Street Map': 'World_Street_Map/MapServer/tile/{Z}/{Y}/{X}',
                    'World Shaded Relief': 'World_Shaded_Relief/MapServer/tile/{Z}/{Y}/{X}',
                    'World Physical Map': 'World_Physical_Map/MapServer/tile/{Z}/{Y}/{X}',
                    'USA Topo Maps': 'USA_Topo_Maps/MapServer/tile/{Z}/{Y}/{X}',
                    'Ocean Basemap': 'Ocean_Basemap/MapServer/tile/{Z}/{Y}/{X}',
                    'NatGeo World Map': 'NatGeo_World_Map/MapServer/tile/{Z}/{Y}/{X}'}

    arcgis_urls = {k: 'https://server.arcgisonline.com/ArcGIS/rest/services/' + v
                   for k, v in arcgis_paths.items()}

    tile_urls = dict(misc_servers, **arcgis_urls)

    # Parameters
    name = param.String(default='Region Settings')

    width = param.Integer(default=900, precedence=-1, doc="Width of the plot in pixels")

    height = param.Integer(default=700, precedence=-1, doc="Height of the plot in pixels")

    zoom_level = param.Integer(default=7, bounds=(1,21), precedence=-1, doc="""
       The zoom level is updated when the bounding box is drawn."""   )

    tile_server = param.ObjectSelector(default=tile_urls['World Imagery'], objects=tile_urls)

    magnification = param.Integer(default=1, bounds=(1,10), precedence=0.1)

    def __init__(self, poly_data=[], **params):
        super().__init__(**params)
        self.boxes = gv.Polygons(poly_data).opts(
            fill_alpha=0.5, color='grey', line_color='white',
            line_width=2, width=self.width, height=self.height
        )
        if not self.boxes:
            self.boxes = self.boxes.opts(global_extent=True)
        self.box_stream = BoxEdit(source=self.boxes, num_objects=1)

    @classmethod
    def bounds_to_zoom_level(cls, bounds, width, height,
                             tile_width=256, tile_height=256, max_zoom=21):
        """
        Computes the zoom level from the lat/lon bounds and the plot width and height

        bounds: tuple(float)
            Bounds in the form (lon_min, lat_min, lon_max, lat_max)
        width: int
            Width of the overall plot
        height: int
            Height of the overall plot
        tile_width: int (default=256)
            Width of each tile
        tile_width: int (default=256)
            Height of each tile
        max_zoom: int (default=21)
            Maximum allowed zoom level
        """

        def latRad(lat):
            sin = math.sin(lat * math.pi / 180);
            if sin == 1:
                radX2 = 20
            else:
                radX2 = math.log((1 + sin) / (1 - sin)) / 2;
            return max(min(radX2, math.pi), -math.pi) / 2;

        def zoom(mapPx, worldPx, fraction):
            return math.floor(math.log(mapPx / worldPx / fraction) / math.log(2));

        x0, y0, x1, y1 = bounds
        latFraction = (latRad(y1) - latRad(y0)) / math.pi
        lngDiff = x1 - x0
        lngFraction = ((lngDiff + 360) if lngDiff < 0 else lngDiff)/360
        latZoom = zoom(height, tile_height, latFraction)
        lngZoom = zoom(width, tile_width, lngFraction)
        return min(latZoom, lngZoom, max_zoom)

    @param.depends('tile_server')
    def callback(self):
        return gv.WMTS(self.tile_server)

    @property
    def bbox(self):
        element = self.box_stream.element if self.box_stream.data else self.boxes
        # Update shared_state with bounding box (if any)
        if element:
            xs, ys = element.array().T
            bbox = (xs[0], ys[0], xs[2], ys[1])
            # Set the zoom level
            zoom_level = self.bounds_to_zoom_level(bbox, self.width, self.height)
            self.zoom_level = zoom_level + self.magnification
            return bbox
        else:
            return None

    # UPDATE wrt earthsim: add the get_image method that replaces the former get_tiff method.
    # get_image uses get_tile_rgb, a new util function from geoviews, while get_tiff
    # required the quest library as an external dependency.
    def get_image(self):
        bbox = self.bbox
        if bbox is None:
            raise ValueError('Please supply a bounding box in order to extract an image.')

        img = gv.util.get_tile_rgb(
            tile_source=self.tile_server, 
            bbox=bbox, 
            zoom_level=self.zoom_level,
            bbox_crs=ccrs.PlateCarree(),
        )

        return img

    def view(self):
        return (gv.DynamicMap(self.callback) * self.boxes).opts(active_tools=['wheel_zoom'])

    @param.output(image=hv.Image)
    def output(self):
        return self.get_image()

    def panel(self):
        return pn.Row(self.param, self.view())


options = Store.options('bokeh')

options.Points = Options('plot', padding=0.1)
options.Path = Options('plot', padding=0.1)
options.Polygons = Options('plot', padding=0.1)
