// Calendar for the ISO local date supplied by the clock module.
#pragma once

#include <gtk-layer-shell.h>
#include <gtkmm.h>

#include <algorithm>
#include <memory>
#include <vector>

namespace waybar::modules {

class ClockCalendar : public Gtk::Window {
 public:
  ClockCalendar() {
    panel_.set_name("clock-calendar");
    grid_.set_column_homogeneous(true);
    panel_.add(grid_);
    panel_.add_events(Gdk::BUTTON_PRESS_MASK);
    panel_.signal_button_press_event().connect([](GdkEventButton*) { return true; }, false);
    layout_.put(panel_, 0, 0);
    add(layout_);
    configure_layer(*this, true);
    signal_key_press_event().connect([this](GdkEventKey* e) {
      if (e->keyval != GDK_KEY_Escape) return false;
      dismiss();
      return true;
    }, false);
  }

  void open(Gtk::Widget& anchor) {
    auto* bar = GTK_WINDOW(gtk_widget_get_toplevel(anchor.gobj()));
    auto* display = gtk_widget_get_display(anchor.gobj());
    auto* monitor = gtk_layer_get_monitor(bar);
    gtk_layer_set_monitor(gobj(), monitor);
    // Other monitors accept an outside click without taking keyboard focus.
    other_outputs_.clear();
    for (int i = 0; i < gdk_display_get_n_monitors(display); ++i) {
      auto* other = gdk_display_get_monitor(display, i);
      if (other == monitor) continue;
      auto& window = other_outputs_.emplace_back(std::make_unique<Gtk::Window>());
      configure_layer(*window, false);
      gtk_layer_set_monitor(window->gobj(), other);
      window->show();
    }
    int x = 0, y = 0, minimum = 0, width = 0;
    gtk_widget_translate_coordinates(anchor.gobj(), GTK_WIDGET(bar), anchor.get_allocated_width() / 2,
                                     anchor.get_allocated_height(), &x, &y);
    GdkRectangle bounds;
    gdk_monitor_get_geometry(monitor, &bounds);
    panel_.show_all();
    panel_.get_preferred_width(minimum, width);
    x += gtk_layer_get_margin(bar, GTK_LAYER_SHELL_EDGE_LEFT) - width / 2;
    y += gtk_layer_get_margin(bar, GTK_LAYER_SHELL_EDGE_TOP);
    layout_.move(panel_, std::clamp(x, 0, std::max(0, bounds.width - width)), y);
    show_all();
  }

  void dismiss() {
    hide();
    for (auto& window : other_outputs_) window->hide();
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
    grid_.show_all();
    return true;
  }

 private:
  void configure_layer(Gtk::Window& window, bool keyboard) {
    window.set_name("clock-calendar-layer");
    auto* w = window.gobj();
    auto* widget = GTK_WIDGET(w);
    gtk_widget_set_visual(widget, gdk_screen_get_rgba_visual(gtk_widget_get_screen(widget)));
    gtk_layer_init_for_window(w);
    gtk_layer_set_namespace(w, "waybar-calendar");
    gtk_layer_set_layer(w, GTK_LAYER_SHELL_LAYER_OVERLAY);
    gtk_layer_set_exclusive_zone(w, -1);
    for (auto edge : {GTK_LAYER_SHELL_EDGE_LEFT, GTK_LAYER_SHELL_EDGE_TOP,
                      GTK_LAYER_SHELL_EDGE_RIGHT, GTK_LAYER_SHELL_EDGE_BOTTOM}) {
      gtk_layer_set_anchor(w, edge, true);
    }
    gtk_layer_set_keyboard_mode(w, keyboard ? GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE
                                            : GTK_LAYER_SHELL_KEYBOARD_MODE_NONE);
    window.add_events(Gdk::BUTTON_PRESS_MASK);
    window.signal_button_press_event().connect([this](GdkEventButton*) {
      dismiss();
      return true;
    }, false);
  }

  Gtk::Label& cell(const std::string& text, const char* style, int col, int row, int width = 1) {
    auto* label = Gtk::make_managed<Gtk::Label>(text);
    label->get_style_context()->add_class(style);
    grid_.attach(*label, col, row, width, 1);
    return *label;
  }

  std::string date_;
  Gtk::Fixed layout_;
  Gtk::EventBox panel_;
  Gtk::Grid grid_;
  std::vector<std::unique_ptr<Gtk::Window>> other_outputs_;
};

}  // namespace waybar::modules
