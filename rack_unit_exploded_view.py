from rack_unit import RackUnit


class RackUnitExplodedView:
    def __init__(self, explosion_distance=5, gap_between_units=15):
        """
        Create an exploded view of multiple rack units

        Args:
            explosion_distance: Distance to explode components
            gap_between_units: Gap between rack units
        """
        self.explosion_distance = explosion_distance
        self.gap_between_units = gap_between_units
        self.rack_units = []
        self.name = "rack_unit_exploded_view"

    def add_rack_unit(
        self,
        depth,
        width,
        height_units=1,
        wall_thickness=0.25,
        floor_thickness=0.125,
        modules_config=None,
        explode=False,
    ):
        """
        Add a rack unit to the view

        Args:
            depth: Depth of the rack unit
            width: Width of the rack unit
            height_units: Height of the rack unit in U units (1U = 1.75")
            wall_thickness: Thickness of the walls
            floor_thickness: Thickness of the floor
            modules_config: Configuration for front modules
            explode: Whether to create the unit in exploded state

        Returns:
            The created RackUnit object
        """
        rack_unit = RackUnit(
            depth,
            width,
            height_units,
            wall_thickness,
            floor_thickness,
            explode=explode,
            explosion_distance=self.explosion_distance,
        )

        # Add front modules based on configuration
        if modules_config == "hdd_bays" or modules_config == "full":
            # Fill all spaces with hard drive bays
            rack_unit.add_hard_drive_bays("all")

        self.rack_units.append(rack_unit)
        return rack_unit

    def arrange(self):
        """Arrange the rack units with front alignment and proper spacing"""
        # Explode all rack units that aren't already exploded
        for rack_unit in self.rack_units:
            if not rack_unit.exploded:
                rack_unit.explode(self.explosion_distance)

        # Calculate y positions
        y_positions = []
        current_y = 0

        for i, rack_unit in enumerate(self.rack_units):
            practical_dims = rack_unit.get_practical_dimensions(self.explosion_distance)

            if i == 0:
                # First unit centered at 0
                y_positions.append(0)
                current_y += practical_dims[1] / 2 + self.gap_between_units
            else:
                # Position based on previous unit's dimensions plus gap
                current_y += practical_dims[1] / 2
                y_positions.append(current_y)
                current_y += practical_dims[1] / 2 + self.gap_between_units

        # Position rack units
        for i, rack_unit in enumerate(self.rack_units):
            y_offset = y_positions[i]
            # No x offset needed - already front-aligned when created
            rack_unit.translate((0, y_offset, 0))
