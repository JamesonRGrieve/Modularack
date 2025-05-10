import cadquery as cq

from abstract_component import AbstractComponent


class AbstractFrontPanelComponent(AbstractComponent):
    """
    An abstract base class for front panel components that can be added to rack units.
    This class handles common functionality including creation, explosion logic, and positioning.
    """

    def __init__(
        self,
        width_segments,
        height_segments,
        depth=1.0,
        name="front_panel",
        explode=False,
        explosion_distance=5,
    ):
        """
        Initialize an abstract front panel component.

        Args:
            width_segments: Number of horizontal segments (1-12)
            height_segments: Number of vertical segments
            depth: Depth of the module in inches
            name: Name of the module
            explode: Whether to explode the object immediately
            explosion_distance: Distance to explode components
        """
        super().__init__(explode, explosion_distance)

        self.width_segments = width_segments
        self.height_segments = height_segments
        self.depth = depth
        self.name = name
        self.position = (0, 0)  # (segment_x, segment_y)
        self.parent_rack = None

        # Create the component
        self._create_components()

        # Explode if requested
        if explode:
            self.explode(explosion_distance)

    def _create_components(self):
        """
        Create the base 3D object for this component.
        This method can be overridden by subclasses to provide custom geometry.
        """
        # This is a basic implementation that creates a simple box
        # Subclasses should override this method with their own specific implementations

        # Note: Actual dimensions will be calculated when create() is called with segment sizes
        return self

    def get_main_object(self):
        """Override to return the panel object as the main object"""
        return self.get_component("panel")

    def create(self, segment_width, segment_height):
        """
        Create the 3D object for this module with actual dimensions.

        Args:
            segment_width: Width of each segment in inches
            segment_height: Height of each segment in inches

        Returns:
            Self for method chaining
        """
        width = self.width_segments * segment_width
        height = self.height_segments * segment_height

        panel_obj = (
            cq.Workplane("YZ").box(width, height, self.depth).translate((0, 0, 0))
        )  # Position at origin initially

        # Update the component
        self.add_component("panel", panel_obj)

        return self

    def translate(self, vector):
        """
        Translate the module by the given vector.

        Args:
            vector: (x, y, z) translation vector

        Returns:
            Self for method chaining
        """
        panel_obj = self.get_component("panel")
        if panel_obj:
            panel_obj = panel_obj.translate(vector)
            self.add_component("panel", panel_obj)

        super().translate(vector)
        return self

    def explode(self, distance=None):
        """
        Explode the component outward by the specified distance.
        For front panel components, this typically means moving forward.

        Args:
            distance: Distance to explode component, defaults to self.explosion_distance

        Returns:
            Self for method chaining
        """
        if distance is None:
            distance = self.explosion_distance

        super().explode(distance)

        # Move the front panel component forward (negative X direction)
        self.translate((-distance * 1.5, 0, 0))

        return self

    def unexplode(self):
        """
        Restore component to its original position.

        Returns:
            Self for method chaining
        """
        if not self.exploded:
            return self

        distance = self.explosion_distance

        # Move the front panel component back to original position
        self.translate((distance * 1.5, 0, 0))

        super().unexplode()
        return self

    def get_practical_dimensions(self, explosion_distance=None):
        """
        Calculate practical dimensions including explosion distances.

        Args:
            explosion_distance: Optional override for explosion distance

        Returns:
            (practical_x, practical_y, practical_z) tuple
        """
        if explosion_distance is None:
            explosion_distance = self.explosion_distance

        # If exploded, the X dimension includes explosion distance
        x_dimension = self.depth + (explosion_distance * 1.5 if self.exploded else 0)

        # Y and Z dimensions are not affected by explosion
        panel_obj = self.get_component("panel")
        if panel_obj:
            bb = panel_obj.BoundingBox()
            return (x_dimension, bb.ylen, bb.zlen)
        else:
            # Default fallback if object hasn't been created yet
            return (x_dimension, 0, 0)
