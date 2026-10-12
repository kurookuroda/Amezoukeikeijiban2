#!/usr/bin/perl
use Encode ();

$copyright = <<EOL;
<!-- 
     Script for amezo-like BBS
     Copyright (C) 1999-2003 amezo_
     http://www17.big.or.jp/~amezo_/
     http://ame.x0.com/
-->
EOL

$amezo = '＠あめぞう';
$urlbase = 'http://ame.x0.com/';
$admin = 'サポート';

# スレッド削除機能の合言葉ハッシュ($6$…=SHA-512 crypt)を置くファイル。
# このファイルが無い/空なら削除機能は誰も使えない(初期状態)。
# .htaccess で web からは読めないようにしてある。
# 設定方法は README.txt の「スレッドの削除」を参照。
$delcryptfile = 'delpass.txt';

$ENV{'SCRIPT_FILENAME'} =~ /\/([^\/]+)$/;
$cgi = $1;
$cgi = 'amezo.cgi' unless $cgi;
if($ENV{'REQUEST_METHOD'} eq 'GET'){
	print "Content-type: text/plain; charset=UTF-8\n\n";
	open(R, "./$cgi");
	print while <R>;
	close(R);
	exit;
}

read(STDIN, $buffer, $ENV{'CONTENT_LENGTH'} || 0);
length($buffer) > 7500 && &error('投稿内容が大きすぎます');
$referer = $ENV{'HTTP_REFERER'};
$referer =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
$referer =~ s{^(https?://)www\.}{$1};   # www. 有りでアクセスされても通す
$referer =~ /^$urlbase([\w\.\-]+)/ || &error('エラー');
$folder = $1;
$origin = $ENV{'HTTP_ORIGIN'};
$origin =~ s{//www\.}{//};
$origin ne '' && index($urlbase, "$origin/") != 0 && &error('不正なリクエストです');

@pairs = split(/&/,$buffer);
foreach $pair (@pairs) {
	($name, $value) = split(/=/, $pair, 2);
	$value =~ tr/+/ /;
	$value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
	$value = &to_utf8($value);
	$value =~ s/&/&amp;/g;
	$value =~ s/\"/&quot;/g;
	$value =~ s/</&lt;/g;
	$value =~ s/>/&gt;/g;
	$value =~ s/'/&#39;/g;
	$value =~ s/\r\n/\r/g;
	$value =~ s/\n/\r/g;
	$value =~ s/\r/<br>/g if $name eq 'comm';
	$value =~ s/[\x00-\x1f]//g;
	$form{$name} = $value;
}

$name = $form{'name'};
$mail = $form{'mail'};
$comm = $form{'comm'};
$subj = $form{'subj'};
$folder = $form{'folder'} if $form{'folder'};
&error('板名が不正です') if $folder eq '' || $folder =~ m{/|\.\.};
$res = $form{'res'};
$form{'sub'} && &res;
$next = $form{'next'};
$next = 1 if !$next;
$next += 20;
$reload = 1 if $name eq $subj && $name eq $comm;
$reload = 1 unless $name || $subj || $comm;
@a = ($comm =~ /<br>/g);
(@a + 0 > 20 || &clen($subj) > 20) && &error("コメントが長すぎます");
$name =~ s/ |　//g;
$name = &ccut($name, 30);
$comm =~ s/&gt;(&gt;)+/&gt;/g;
$subj =~ s/ |　|＿//g;

$comm2 = $comm;
$comm2 =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
if(open(R, "./ng.txt")){   # ng.txt が無ければ NGワード処理は省略
while(<R>){
	chop;
	($ng, $opt) = split(/,/);
	$ng =~ s/(\W)/\\$1/g;
	if($opt eq 'n'){
		$reload = 1 if $name =~ /$ng/;
	}elsif($opt eq 'c'){
		$reload = 1 if $comm2 =~ /$ng/;
	}else{
		$name =~ s/$ng//g;$comm =~ s/$ng//g;$mail =~ s/$ng//g;$subj =~ s/$ng//g;
	}
}
close(R);
}

if($next == 21 && !$reload){

$_ = $admin;
s/(\W)/\\$1/g;
$name =~ s/$_/＃$admin/g;

$delcrypt = &load_delcrypt;
$delcrypt ne '' && crypt($name, $delcrypt) eq $delcrypt && &del;
$res && undef $subj;
$name || &error("投稿者を記入してください");
$comm || &error("コメントが入力されていません");
$res || $subj || &error("題名が入力されていません");
&check if $subj;

$comm =~ s/(https?\:[\w\.\~\-\/\?\+\=\:\@\%\;\#\&]+)/&url($1)/eg;
$mail && ($name = "<a href=\"mailto\:$mail \">$name </a>");
($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime(time);
$month = ($mon + 1);
$year %= 100;
$year < 10 && ($year = "0$year");
$month < 10 && ($month = "0$month");
$mday < 10 && ($mday = "0$mday");
$sec < 10 && ($sec = "0$sec");
$min < 10 && ($min = "0$min");
$hour < 10 && ($hour = "0$hour");
$wday = ("日", "月", "火", "水", "木", "金", "土")[$wday];
$date = "20$year年$month月$mday日($wday)$hour時$min分$sec秒";
$res = "$year$month$mday$hour$min$sec" unless $res;
exit if $res =~ /\D/;
#exit if length($comm) < 5;

$file = "./$folder/$res.html";
open(W, "+< $file") || $subj && open(W, "> $file") || &error('スレッドがありません.');
flock(W, 2);
while(<W>){
	last unless /<dt>(\d+)/;
	$cnt = $1;
	$pos = tell(W);
	$prev = $_;
}
seek(W, $pos, 0);
$cnt++;

$prev =~ /<b>(.+) <\/b>.+<dd>(.+) <\/dl>/;
$name eq $1 && $comm eq $2 && print W && &error('二重カキコです.');
if($subj){
	$subj1 = "<title>$subj </title>";
	$subj2 = "<font size=+2 color=red><b>$subj </b></font>";
}
$line = <<EOL;
$subj1<dl><dt>$cnt$subj2投稿者：<font color=forestgreen><b>$name </b></font>
<font size=-1>　投稿日：$date</font><br><dd>$comm </dl>
EOL
$line =~ s/\n//g;
print W "$line\n";
$line = <<EOL;
<form method=post action="../$cgi">
<input type=hidden name="res" value="$res">
投稿者 <input type=text name="name" size=20>
メール <input type=text name="mail" size=20><br>
<input type=submit value="↑へのレスカキコ" ><br>
<textarea name="comm" rows=4 cols=70 ></textarea>
</form>
EOL
$line =~ s/\n//g;
print W "$line\n";
flock(W, 8);
close(W);

}

open(R, "./blist.txt");
while(<R>){
	chop;
	($fol, $color, $title) = split(/,/);
	last if $fol eq $folder;
}
close(R);

$page = '2' if $next != 21;
$index = "index$page.html";
$file = "./$folder/$index";
$main = "(メイン)" if $folder eq 'main';
($color, $bg) = split(/!/, $color);
$bg = " background=\"$bg\"" if $bg;
if ($color =~ /\*$/){
	$text = q( text="#ffffff" link="red" vlink="orange");
	chop $color;
}
$title =~ s/#c#/,/g;
$title0 = $title;
if($title0 =~ /alt=\"([^\"]+)/){
	$title0 = $1;
	undef $amezo;
}

if($next == 21){
	$time = time;
	open(K, "./$folder/lasttime.txt");
	$lasttime = <K>;
	close(K);
	&redirect if $time - $lasttime < 5;
	open(K, "> ./$folder/lasttime.txt");
	print K "$time";
	close(K);
}

open(W, "+< $file");
&redirect unless flock(W, 6);

print W <<EOF;
<html><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title0$amezo$main</title></head>
$copyright
<body$bg bgcolor="$color"$text>
<font size=+2>$title$amezo$main</font>
EOF

open(R, "./header.html");
print W while <R>;
close(R);

print W <<EOF;
<form method=post action="../$cgi">
<input type=submit value="次のページ">
<input type=text name="next" value="$next" size="3">〜</form>
<font size=2>
<!-- HEAD LINE -->
EOF

opendir(DIR, "./$folder");
@dir = readdir(DIR);
closedir(DIR);

for($i=0;$dir[$i];$i++){
	$ts = ($dir[$i] =~ /^\d+\.html/) ?
		(stat("./$folder/$dir[$i]"))[9] - 800000000 : ' ';
	$dir[$i] = "$ts,$dir[$i]";
}
@dir = sort {$b cmp $a;} @dir;

for($i=$next - 21;$i < $next+100-21 && $dir[$i];$i++){
	($ts, $file) = split(/,/, $dir[$i]);
	last if $ts eq ' ';
	open(R, "./$folder/$file");
	$_ = <R>;
	close(R);
	/<b>([^\<]*)<\/b>/;
	$j = $i+1;
	print W " $j<a href=\"$file\">$1</a>\n";
}
print W "<!-- HEAD LINE END -->\n</font>\n";

for($i=$next - 21;$i < $next - 1 && $dir[$i];$i++){
	($ts, $file) = split(/,/, $dir[$i]);
	last if $ts eq ' ';
	print W <<EOL;
<table border=1 cellspacing=1 cellpadding=2 width=100% bgcolor="#efefef"><tr><td><font color="#000000">
EOL
	open(R, "./$folder/$file");
	$_ = <R>;
	s/<title>.*<\/title>//;
	print W;
	for($j=0;<R>;$j++){
		last if /^<form/; 
		$lines[$j % 7] = $_;
	}
	close(R);
	$k = $j - 7;
	$k = 0 if $k < 0;
	for($m=$k;$m < $j;$m++){
		print W "$lines[$m % 7]";
	}
	$file =~ /(.+)\.html/;
	$res = $1;
	undef $sub;
	$k = $j - 98;
	$sub = <<EOL if $j > 200;
<input type=text name="from" value="$k" size="4">
<input type=submit name="sub" value="〜">　
EOL
	print W <<EOL;
</font></td></tr></table>
<form method=post action="../$cgi">
<input type=hidden name="res" value="$res">
投稿者 <input type=text name="name" size=20>
メール <input type=text name="mail" size=20><br>
<input type=submit value="↑へのレスカキコ" >
<a href="$res.html">レス全部を見る</a>
$sub<a href="#top">上へ　</a><a href="./">リロード</a><br>
<textarea name="comm" rows=4 cols=70 ></textarea>
</form><hr>
EOL

}

print W <<EOF;
<form method=post action="../$cgi">
<input type=submit value="次のページ">
<input type=text name="next" value="$next" size="3">〜</form>
<hr></body></html>
EOF

truncate(W, tell(W));
flock(W, 8);
close(W);
&redirect;

sub redirect {
	undef $index unless $page;
	print "Location: $urlbase$folder/$index\n\n\n";
	exit;
}

sub url {
	$url = $dsp = $_[0];
	$url =~ s/&amp;/&/g;
	"<a href=\"$url\" target=\"_blank\" rel=\"noopener noreferrer nofollow\">$dsp</a>";
}

sub error {
	print "Content-type: text/html; charset=UTF-8\n\n<html><head>"
		. '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">'
		. "</head><body><h2>$_[0]</h2></body></html>";
	exit;
}

sub res {
	print "Content-type: text/html; charset=UTF-8\n\n";
	open(R, "./$folder/$res.html");
	print <R>."";
	while(<R>){
		/<dt>(\d+)/;
		last if $1 >= $form{'from'};
	}
	print;
	$fol = "<input type=hidden name=\"folder\" value=\"$folder\">";
	while(<R>){
		if(/<\/form>/){
			s/(action=\")\.\.\//$1/;
			s/(<\/form>)/$fol$1/;
		}
		print;
	}
	exit;
}

sub del {
	if($mail){
		$name = $admin;
		undef $mail unless $mail =~ /\@/;
		return;
	}
	print "Content-type: text/html\n\n";
	exit unless $res;
	$file = "./$folder/$res.html";
	if(!$comm){
#		unlink($file);
		$newfile = "./$folder/x$res.html";
		rename($file, $newfile);
		chmod 0600, $newfile;
		exit;
	}
	$comm = ',' . $comm . ',';
	$comm =~ s/(\d+)\-(\d+)/join(',',($1..$2))/eg;
	$comm =~ s/<br>/,/g;
	$ts = (stat($file))[9];
	open(R, $file);
	@lines = <R>;
	close(R);
	open(W, "+> $file");
	flock(W, 2);
	foreach(@lines){
		next if /<dt>(\d+)/ && ($n=','.$1.',') && $comm =~ /$n/;
		($year,$mon,$mday,$hour,$min,$sec) = ($1,$2,$3,$4,$5,$6) 
			if /(\d\d\d\d).{3}(\d\d).{3}(\d\d).{3}\(.{3}\)(\d\d).{3}(\d\d).{3}(\d\d)/;
		print W;
	}
	close(W);
	$year -= 1900;
	$mon--;
	$uru = int(($year - 72) / 4);
	if (((($year + 1900) % 4) == 0) && ($mon < 2)) { $uru--; }
	$ts = $year - 70;
	$ts = $ts * 365 + (0,31,59,90,120,151,181,212,243,273,304,334)[$mon] + $mday + $uru;
	$ts = $ts * 24 + $hour - 9;
	$ts = $ts * 60 + $min;
	$ts = $ts * 60 + $sec;
	$ts -= $1*24*60*60 if $comm =~ /p(\d+)/;
	utime $ts+1, $ts+1, $file;
	chmod 0404, $file if $comm =~ /x/;
	exit;
}

sub check {
	$ip = $ENV{'REMOTE_ADDR'};
	$time = time;
	open(Z, "global.mem");
	while(<Z>){
		chop;
		($ip_o, $time_o) = split;
		$iplist{$ip_o} = $time_o if $time - $time_o < 180;
	}
	close(Z);
	if($iplist{$ip}){
		$remain = 180 - ($time - $iplist{$ip});
		&error("あと " . $remain . "秒たってから投稿してください");
	}
	$iplist{$ip} = $time;
	open(Z, "> global.mem");
	for (keys %iplist){
		print Z "$_ $iplist{$_}\n";
	}
	close(Z);
	chmod 0600, "global.mem";
}

# ---------------------------------------------------------------------------
# UTF-8 版で追加したヘルパ
# ---------------------------------------------------------------------------

# 注意: Encode::decode は CHECK を渡すと第2引数を「消費」して空にしてしまう。
#       元の値を壊さないよう、必ずコピーを渡すこと。
sub decode_bytes {
	my ($enc, $str) = @_;
	my $src = $str;
	my $dec;
	return $dec if eval { $dec = Encode::decode($enc, $src, Encode::FB_CROAK()); 1 };
	return undef;
}

# 受け取ったバイト列を UTF-8 に揃える。
# 妥当な UTF-8 ならそのまま、そうでなければ CP932(Shift_JIS)とみなして変換する。
sub to_utf8 {
	my ($str) = @_;
	return '' unless defined $str;
	my $dec = &decode_bytes('UTF-8', $str);
	$dec = &decode_bytes('cp932', $str) unless defined $dec;
	return Encode::encode('UTF-8', $dec) if defined $dec;
	(my $out = $str) =~ s/[\x80-\xff]//g;
	return $out;
}

# 文字数を返す(バイト数ではなく)。
sub clen {
	my ($str) = @_;
	return 0 unless defined $str;
	my $dec = &decode_bytes('UTF-8', $str);
	return defined $dec ? length($dec) : length($str);
}

# 先頭から指定文字数で切り詰める。多バイト文字を途中で割らない。
sub ccut {
	my ($str, $max) = @_;
	return '' unless defined $str;
	my $dec = &decode_bytes('UTF-8', $str);
	return substr($str, 0, $max) unless defined $dec;
	return Encode::encode('UTF-8', substr($dec, 0, $max));
}

# 削除機能の合言葉ハッシュを別ファイルから読む。
# ファイルが無い/空なら空文字を返し、削除機能は無効になる。
sub load_delcrypt {
	local $/;
	open(my $f, '<', $delcryptfile) or return '';
	my $c = <$f>;
	close($f);
	return '' unless defined $c;
	$c =~ s/^\s+//;
	$c =~ s/\s+$//;
	return $c;
}
