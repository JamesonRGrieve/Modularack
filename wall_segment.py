import cadquery as cq

from abstract_component import AbstractComponent


class WallSegment(AbstractComponent):
    """A segment of a rack unit wall with configurable height (1U or 2U)"""

    POSITIONS = ["front", "back", "left", "right"]

    def __init__(
        self,
        wall_type,
        width,
        depth,
        height_units=1,
        thickness=0.25,
        name=None,
        explode=False,
        explosion_distance=5,
    ):
        """
        Create a wall segment

        Args:
            wall_type: Type of wall ("front", "back", "left", "right")
            width: Width of the wall
            depth: Depth of the rack unit (used for side walls)
            height_units: Height in U units (1 or 2 only)
            thickness: Thickness of the wall
            name: Name of the segment
            explode: Whether to explode the object immediately
            explosion_distance: Distance to explode components
        """
        if height_units not in [1, 2]:
            raise ValueError("Wall segment height_units must be 1 or 2")

        if wall_type not in self.POSITIONS:
            raise ValueError(f"Wall type must be one of {self.POSITIONS}")

        super().__init__(explode, explosion_distance)

        self.wall_type = wall_type
        self.width = width
        self.depth = depth
        self.height_units = height_units
        self.height = height_units * 1.75  # 1U = 1.75 inches
        self.thickness = thickness
        self.name = name or f"{wall_type}_wall_{height_units}U"

        # Create the component
        self._create_components()

        # Explode if requested
        if explode:
            self.explode(explosion_distance)

    def _create_components(self):
        """Create the wall segment"""
        if self.wall_type in ["front", "back"]:
            # Front and back walls are thin in X dimension, full width in Y
            wall_obj = (
                cq.Workplane("XY")
                .box(self.thickness, self.width, self.height)
                .translate((0, 0, self.height / 2))
            )  # Center at origin initially
        else:
            # Side walls (left/right) are thin in Y dimension, partial depth in X
            wall_obj = (
                cq.Workplane("XY")
                .box(self.depth - 2 * self.thickness, self.thickness, self.height)
                .translate((0, 0, self.height / 2))
            )  # Center at origin initially

        # Add to components dictionary
        self.add_component("wall", wall_obj)

        return self

    def get_main_object(self):
        """Override to return the wall object as the main object"""
        return self.get_component("wall")

    def get_practical_dimensions(self, explosion_distance=None):
        """Get practical dimensions of the wall segment"""
        if explosion_distance is None:
            explosion_distance = self.explosion_distance

        if self.wall_type in ["front", "back"]:
            return (
                self.thickness + (explosion_distance if self.exploded else 0),
                self.width,
                self.height,
            )
        else:
            return (
                self.depth
                - 2 * self.thickness
                + (explosion_distance if self.exploded else 0),
                self.thickness,
                self.height,
            )

    def explode(self, distance=None):
        """Explode the wall segment in the appropriate direction"""
        if distance is None:
            distance = self.explosion_distance

        super().explode(distance)

        # Direction depends on wall type
        if self.wall_type == "front":
            self.translate((-distance, 0, 0))
        elif self.wall_type == "back":
            self.translate((distance, 0, 0))
        elif self.wall_type == "left":
            self.translate((0, -distance, 0))
        elif self.wall_type == "right":
            self.translate((0, distance, 0))

        return self

    def unexplode(self):
        """Return wall segment to its original position"""
        if not self.exploded:
            return self

        distance = self.explosion_distance

        # Direction depends on wall type
        if self.wall_type == "front":
            self.translate((distance, 0, 0))
        elif self.wall_type == "back":
            self.translate((-distance, 0, 0))
        elif self.wall_type == "left":
            self.translate((0, distance, 0))
        elif self.wall_type == "right":
            self.translate((0, -distance, 0))

        super().unexplode()
        return self

    def translate(self, vector):
        """Translate the wall segment"""
        wall_obj = self.get_component("wall")
        if wall_obj:
            wall_obj = wall_obj.translate(vector)
            self.add_component("wall", wall_obj)

        super().translate(vector)
        return self
