package com.taskmaster.android;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.*;
import android.widget.*;
import com.taskmaster.android.model.TaskNode;

import java.util.*;

public class TaskAdapter extends BaseAdapter {
    private Context ctx;
    private List<TaskNode> items = new ArrayList<>();
    private OnToggleDone onToggleDone;

    public interface OnToggleDone { void toggle(TaskNode task, int position); }

    public TaskAdapter(Context ctx, OnToggleDone cb) {
        this.ctx = ctx;
        this.onToggleDone = cb;
    }

    public void setItems(List<TaskNode> list) {
        items = new ArrayList<>(list);
        notifyDataSetChanged();
    }

    @Override public int getCount() { return items.size(); }
    @Override public TaskNode getItem(int i) { return items.get(i); }
    @Override public long getItemId(int i) { return i; }

    @Override
    public View getView(int pos, View v, ViewGroup parent) {
        if (v == null) v = LayoutInflater.from(ctx).inflate(R.layout.item_task, parent, false);
        final TaskNode t = items.get(pos);
        final int fpos = pos;

        View indentView = (View) v.findViewById(R.id.indent);
        ViewGroup.LayoutParams p = indentView.getLayoutParams();
        p.width = dpToPx(t.depth * 20);
        indentView.setLayoutParams(p);

        CheckBox cb = (CheckBox) v.findViewById(R.id.taskCheckbox);
        cb.setOnCheckedChangeListener(null);
        cb.setChecked(t.isDone());
        cb.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            public void onCheckedChanged(CompoundButton b, boolean checked) {
                onToggleDone.toggle(t, fpos);
            }
        });

        TextView title = (TextView) v.findViewById(R.id.taskTitle);
        title.setText(t.title);
        if (t.isDone()) {
            title.setPaintFlags(title.getPaintFlags() | Paint.STRIKE_THRU_TEXT_FLAG);
            title.setTextColor(Color.parseColor("#9E9E9E"));
        } else {
            title.setPaintFlags(title.getPaintFlags() & ~Paint.STRIKE_THRU_TEXT_FLAG);
            title.setTextColor(Color.parseColor("#212121"));
        }

        TextView prio = (TextView) v.findViewById(R.id.taskPriority);
        prio.setText(String.valueOf(t.priority));
        prio.setBackgroundColor(priorityColor(t.priority));

        TextView status = (TextView) v.findViewById(R.id.taskStatus);
        status.setText(t.statusLabel());
        status.setBackgroundColor(statusBgColor(t.status));

        StringBuilder sb = new StringBuilder();
        if (!t.category.isEmpty()) sb.append(t.category);
        if (!t.tags.isEmpty()) {
            if (sb.length() > 0) sb.append(" - ");
            int max = Math.min(2, t.tags.size());
            for (int i = 0; i < max; i++) {
                if (i > 0) sb.append(", ");
                sb.append("#").append(t.tags.get(i));
            }
        }
        TextView meta = (TextView) v.findViewById(R.id.taskMeta);
        String metaStr = sb.toString();
        meta.setText(metaStr);
        meta.setVisibility(metaStr.isEmpty() ? View.GONE : View.VISIBLE);

        View flagView = (View) v.findViewById(R.id.flagIndicator);
        flagView.setVisibility(t.flag ? View.VISIBLE : View.GONE);

        TextView childCount = (TextView) v.findViewById(R.id.childCount);
        if (!t.children.isEmpty()) {
            childCount.setVisibility(View.VISIBLE);
            childCount.setText("> " + t.children.size());
        } else {
            childCount.setVisibility(View.GONE);
        }

        return v;
    }

    private int priorityColor(int p) {
        float frac = (p - 1) / 9f;
        int r = (int)(220 * frac);
        int g = (int)(150 * (1 - frac));
        return Color.argb(220, r, g + 50, 30);
    }

    private int statusBgColor(String s) {
        switch (s) {
            case "in_progress": return Color.parseColor("#1565C0");
            case "blocked":     return Color.parseColor("#B71C1C");
            case "done":        return Color.parseColor("#2E7D32");
            default:            return Color.parseColor("#757575");
        }
    }

    private int dpToPx(int dp) {
        float d = ctx.getResources().getDisplayMetrics().density;
        return (int)(dp * d + 0.5f);
    }
}
