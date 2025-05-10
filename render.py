from abstract_component import AbstractComponent
from rack_unit import RackChassis


def show_component(component, name_suffix=""):
    """
    Show a component or explodable object in the viewer without redundancy

    Args:
        component: Component or AbstractComponent to show
        name_suffix: Suffix to add to the name for identification
    """
    if isinstance(component, AbstractComponent):
        # Show always-visible components regardless of child components
        always_visible = component.get_always_visible_components()
        for comp_name, comp_obj in always_visible.items():
            show_object(comp_obj, name=f"{component.name}_{comp_name}_{name_suffix}")

        # For AbstractComponents with children, show the children
        if component.child_components:
            # Recursively show all child components
            for child_name, child_comp in component.child_components.items():
                show_component(child_comp, f"{name_suffix}_{child_name}")
        else:
            # Only show individual components if there are no child components
            # Skip components that were already shown as always-visible
            for comp_name, comp_obj in component.components.items():
                if comp_name not in always_visible:
                    show_object(
                        comp_obj, name=f"{component.name}_{comp_name}_{name_suffix}"
                    )
    else:
        # It's a simple object
        obj_name = getattr(component, "name", "object")
        show_object(component, name=f"{obj_name}_{name_suffix}")


class RackUnitExplodedView:
    """
    A view that arranges multiple rack units with proper spacing
    """

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
        rack_unit = RackChassis(
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

    def show(self):
        """Show all rack units"""
        for rack_unit in self.rack_units:
            show_component(
                rack_unit, name_suffix=f"{rack_unit.depth}_{rack_unit.height_units}U"
            )


# Main code
if __name__ == "__main__" or True:  # True to ensure this runs in any environment
    # Rack dimensions
    rack_total_width = 19
    rack_chassis_width = 17.75
    rack_ear_width = rack_total_width - rack_chassis_width
    rack_unit_depths = [36, 42, 48, 50]

    # Create exploded view
    view = RackUnitExplodedView(explosion_distance=5, gap_between_units=15)

    # Add rack units with different heights but all with full drive bay populations
    # 1U
    view.add_rack_unit(
        rack_unit_depths[0], rack_chassis_width, 1, modules_config="full", explode=True
    )

    # 2U
    view.add_rack_unit(
        rack_unit_depths[1], rack_chassis_width, 2, modules_config="full", explode=True
    )

    # 3U (new)
    view.add_rack_unit(
        rack_unit_depths[2], rack_chassis_width, 3, modules_config="full", explode=True
    )

    # 4U
    view.add_rack_unit(
        rack_unit_depths[3], rack_chassis_width, 4, modules_config="full", explode=True
    )

    # Arrange and show
    view.arrange()
    view.show()
