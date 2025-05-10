import cadquery as cq


class FrontModule:
    """A module that can be added to the front panel of a rack unit"""

    def __init__(self, width_segments, height_segments, depth=1.0, name="module"):
        """
        Create a front panel module

        Args:
            width_segments: Number of horizontal segments (1-12)
            height_segments: Number of vertical segments
            depth: Depth of the module in inches
            name: Name of the module
        """
        self.width_segments = width_segments
        self.height_segments = height_segments
        self.depth = depth
        self.name = name
        self.object = None
        self.position = (0, 0)  # (segment_x, segment_y)
        self.parent_rack = None

    def create(self, segment_width, segment_height):
        """
        Create the 3D object for this module

        Args:
            segment_width: Width of each segment in inches
            segment_height: Height of each segment in inches
        """
        width = self.width_segments * segment_width
        height = self.height_segments * segment_height

        self.object = (
            cq.Workplane("YZ").box(width, height, self.depth).translate((0, 0, 0))
        )  # Position at origin initially

        return self

    def translate(self, vector):
        """Translate the module by the given vector"""
        if self.object:
            self.object = self.object.translate(vector)
        return self


class HardDriveBay(FrontModule):
    """A 3.5" hard drive bay module (1 segment high, 3 segments wide)"""

    def __init__(self, name="hdd_bay"):
        super().__init__(width_segments=3, height_segments=1, depth=1.5, name=name)

    def create(self, segment_width, segment_height):
        """Override to create a more detailed hard drive bay"""
        width = self.width_segments * segment_width
        height = self.height_segments * segment_height

        # Create basic shape
        self.object = (
            cq.Workplane("YZ").box(width, height, self.depth).translate((0, 0, 0))
        )

        # Add handle cutout
        handle_width = width * 0.8
        handle_height = height * 0.6
        handle_depth = self.depth * 0.3

        self.object = (
            self.object.faces(">X")  # Select front face
            .workplane()
            .rect(handle_width, handle_height)
            .cutBlind(-handle_depth)
        )

        return self
