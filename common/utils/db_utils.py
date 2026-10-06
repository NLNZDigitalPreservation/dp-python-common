def _puzzle_basic_type(
    ary_conditions, table_field_name, table_field_values, match_str_with_equal=False
):
    if table_field_values is None:
        return ary_conditions

    if (
        isinstance(table_field_values, int)
        or isinstance(table_field_values, float)
        or isinstance(table_field_values, bool)
    ):
        sql_condition = f"{table_field_name}={table_field_values}"
    elif isinstance(table_field_values, str):
        if match_str_with_equal:
            sql_condition = f"{table_field_name} = '{table_field_values}'"
        else:
            sql_condition = f"{table_field_name} like '%{table_field_values}%'"
    else:
        raise RuntimeError(f"Unknown type: {type(table_field_values)}")

    ary_conditions.append(sql_condition)
    return ary_conditions


def puzzle_sql_condition(ary_conditions, table_field_name, table_field_values):
    if table_field_values is None:
        return ary_conditions

    if isinstance(table_field_values, list):
        if len(table_field_values) == 1:
            return _puzzle_basic_type(
                ary_conditions,
                table_field_name,
                table_field_values[0],
                match_str_with_equal=True,
            )
        elif len(table_field_values) > 1:
            sql_condition = f"{table_field_name} in {tuple(table_field_values)}"
            ary_conditions.append(sql_condition)
    else:
        return _puzzle_basic_type(ary_conditions, table_field_name, table_field_values)

    return ary_conditions


class SqlConditionPuzzle:
    def __init__(self):
        self.ary_conditions = []

    def add(self, table_field_name, table_field_values):
        puzzle_sql_condition(self.ary_conditions, table_field_name, table_field_values)

    @property
    def sql_conditions(self):
        if len(self.ary_conditions) == 0:
            return ""

        return " and ".join(self.ary_conditions)
