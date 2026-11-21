// Shared audio frames, painted by each horizontal bar beneath its module box.
#pragma once

#include <gtkmm.h>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <memory>

#include "util/command_line_stream.hpp"

namespace waybar {

class Spectrum {
 public:
  static std::shared_ptr<Spectrum> acquire(const std::string& command) {
    static std::weak_ptr<Spectrum> shared;
    auto spectrum = shared.lock();
    if (!spectrum) {
      spectrum.reset(new Spectrum(command));
      shared = spectrum;
    }
    return spectrum;
  }

  ~Spectrum() {
    tick_.disconnect();
    retry_.disconnect();
  }

  sigc::signal<void> changed;

  void draw(const Cairo::RefPtr<Cairo::Context>& cr, Gtk::Box& box, Gtk::Window& window) const {
    if (!visible_) return;
    const double w = box.get_allocated_width(), h = box.get_allocated_height();
    if (w < 2 || h < 2) return;
    auto style = window.get_style_context();
    Gdk::RGBA ink("#d891ed");
    style->lookup_color("desktop_lavender", ink);

    // box is allocated inside the window's border. Clip the wave to the inner corners.
    int radius = 0;
    gtk_style_context_get(style->gobj(), GTK_STATE_FLAG_NORMAL, GTK_STYLE_PROPERTY_BORDER_RADIUS,
                          &radius, nullptr);
    const double r = std::clamp(radius - 1., 0., std::min(w, h) / 2);
    cr->save();
    cr->begin_new_path();
    cr->arc(w-r, r, r, -G_PI_2, 0);
    cr->arc(w-r, h-r, r, 0, G_PI_2);
    cr->arc(r, h-r, r, G_PI_2, G_PI);
    cr->arc(r, r, r, G_PI, 3*G_PI_2);
    cr->close_path();
    cr->clip();

    const double peak = std::min(22., h * .60);
    const double step = w / (levels_.size() - 1);
    double y = h - peak * levels_.front();
    cr->move_to(0, h);
    cr->line_to(0, y);
    for (size_t i = 1; i < levels_.size(); ++i) {
      const double mid = (i - .5) * step;
      const double next = h - peak * levels_[i];
      cr->curve_to(mid, y, mid, next, i * step, next);
      y = next;
    }
    cr->line_to(w, h);
    cr->close_path();
    auto fill = Cairo::LinearGradient::create(0, h, 0, h - peak);
    fill->add_color_stop_rgba(0, ink.get_red(), ink.get_green(), ink.get_blue(), .19);
    fill->add_color_stop_rgba(1, ink.get_red(), ink.get_green(), ink.get_blue(), .08);
    cr->set_source(fill);
    cr->fill();
    cr->restore();
  }

 private:
  using Bands = std::array<double, 64>;
  using Clock = std::chrono::steady_clock;
  std::string command_;
  Bands target_{}, levels_{};
  Clock::time_point last_sound_{};
  bool visible_ = false;
  sigc::connection tick_, retry_;
  util::command::LineStream stream_;

  explicit Spectrum(std::string command)
      : command_(std::move(command)),
        stream_("", [this](const std::string& line) { frame(line); }, [this](int) {
          retry_ = Glib::signal_timeout().connect_seconds([this] {
            stream_.start(command_);
            return false;
          }, 2);
        }) {
    stream_.start(command_);
  }

  void frame(const std::string& line) {
    Bands next{};
    const char* p = line.data();
    const char* end = p + line.size();
    for (double& value : next) {
      unsigned raw = 0;
      auto [stop, err] = std::from_chars(p, end, raw);
      if (err != std::errc{} || raw > 255 || (stop != end && *stop != ';')) return;
      value = raw > 2 ? raw / 255. : 0.;
      p = stop == end ? end : stop + 1;
    }
    if (p != end || std::ranges::max(next) == 0) return;
    target_ = next;
    last_sound_ = Clock::now();
    if (!tick_.connected()) {
      tick_ = Glib::signal_timeout().connect([this] { return animate(); }, 42);
    }
  }

  bool animate() {
    using namespace std::chrono_literals;
    const auto age = Clock::now() - last_sound_;
    visible_ = age < 1s;
    for (size_t i = 0; i < levels_.size(); ++i) {
      const double goal = age < 100ms ? target_[i] : 0.;
      levels_[i] += (goal - levels_[i]) * (goal > levels_[i] ? .65 : .18);
    }
    if (!visible_) levels_.fill(0);
    changed.emit();  // Includes the final clear, then leaves the GTK clock idle.
    return visible_;
  }
};

}  // namespace waybar
