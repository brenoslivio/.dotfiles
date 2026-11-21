// Calendar for the ISO local date supplied by the clock module.
#pragma once

#include <gtkmm.h>

namespace waybar::modules {

class ClockCalendar : public Gtk::Menu {
 public:
  ClockCalendar() {
    set_name("clock-calendar");
    set_reserve_toggle_size(false);
    grid_.set_column_homogeneous(true);
    item_.add(grid_);
    append(item_);
  }

  void open(Gtk::Widget& anchor, GdkEventButton* event) {
    // Position relative to the bar's layer surface, including its monitor origin.
    auto* bar = gtk_widget_get_toplevel(anchor.gobj());
    GdkRectangle edge{0, 0, anchor.get_allocated_width(), 1};
    gtk_widget_translate_coordinates(anchor.gobj(), bar, 0, anchor.get_allocated_height(),
                                     &edge.x, &edge.y);
    gtk_menu_popup_at_rect(gobj(), gtk_widget_get_window(bar), &edge, GDK_GRAVITY_NORTH,
                           GDK_GRAVITY_NORTH, reinterpret_cast<GdkEvent*>(event));
  }

  bool display(const std::string& iso_date) {
    if (iso_date == date_ && !date_.empty()) return true;
    g_autoptr(GDateTime) date = g_date_time_new_from_iso8601((iso_date + "T12:00:00Z").c_str(), nullptr);
    if (!date) return false;
    date_ = iso_date;
    for (auto* child : grid_.get_children()) grid_.remove(*child);

    const int year = g_date_time_get_year(date), month = g_date_time_get_month(date);
    const int today = g_date_time_get_day_of_month(date);
    g_autoptr(GDateTime) first = g_date_time_new_utc(year, month, 1, 12, 0, 0);
    const int offset = g_date_time_get_day_of_week(first) - 1;
    g_autofree gchar* title = g_date_time_format(date, "%B %Y");
    cell(title, "month-title", 0, 0, 7);
    for (int col = 0; col < 7; ++col) {
      g_autoptr(GDateTime) weekday = g_date_time_add_days(first, col - offset);
      g_autofree gchar* name = g_date_time_format(weekday, "%a");
      cell(name, "weekday", col, 1);
    }
    const int days = g_date_get_days_in_month(static_cast<GDateMonth>(month), year);
    for (int day = 1; day <= days; ++day) {
      const int pos = offset + day - 1;
      auto& label = cell(std::to_string(day), "day", pos % 7, 2 + pos / 7);
      if (day == today) label.get_style_context()->add_class("today");
    }
    item_.show_all();
    return true;
  }

 private:
  Gtk::Label& cell(const std::string& text, const char* style, int col, int row, int width = 1) {
    auto* label = Gtk::make_managed<Gtk::Label>(text);
    label->get_style_context()->add_class(style);
    grid_.attach(*label, col, row, width, 1);
    return *label;
  }

  std::string date_;
  Gtk::MenuItem item_;
  Gtk::Grid grid_;
};

}  // namespace waybar::modules
