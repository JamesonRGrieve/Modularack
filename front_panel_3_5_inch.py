import cadquery as cq

from abstract_front_panel_component import AbstractFrontPanelComponent


class FrontPanel3_5Inch(AbstractFrontPanelComponent):
    """A 3.5 inch hard drive bay module (1 segment high, 3 segments wide)"""

    def __init__(
        self,
        name="3.5inch_bay",
        explode=False,
        explosion_distance=5,
    ):
        """
        Create a 3.5 inch front panel module

        Args:
            name: Name of the module
            explode: Whether to explode the object immediately
            explosion_distance: Distance to explode components
        """
        super().__init__(
            width_segments=3,
            height_segments=1,
            depth=1.5,
            name=name,
            explode=explode,
            explosion_distance=explosion_distance,
        )

    def create(self, segment_width, segment_height):
        """
        Override to create a more detailed 3.5 inch bay

        Args:
            segment_width: Width of each segment in inches
            segment_height: Height of each segment in inches

        Returns:
            Self for method chaining
        """
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

        # Update the component
        self.add_component("panel", self.object)

        return self
